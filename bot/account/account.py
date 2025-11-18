import json
import time

import requests
from tqdm import tqdm
from pathlib import Path
from bs4 import BeautifulSoup
from collections import defaultdict

from tools.rate_limiter import rate_limited
from utils import handle_status_codes_using_attempts
from tools import BasicLogger

from enums import Urls
from enums import Config
from bot.account.market_item_stats import MarketItemStats
from bot.account.summarize_to_excel import SummarizeToExcel
from utils.exceptions import TooManyRequestsError


class Account(BasicLogger):
    """
        Все функции, связанные так или иначе с аккаунтом, но не требующие
        выбора определённой игры
    """
    def __init__(self) -> None:
        super().__init__(
            logger_name=f"{self.__class__.__name__}",
            dir_specify="account",
            file_name=f"{self.__class__.__name__}"
        )
        self.excel_maker = SummarizeToExcel()

    @handle_status_codes_using_attempts()
    @rate_limited(1)
    def get_account_page(self, session: requests.Session) -> requests.Response:
        url = Urls.ACCOUNT
        headers = {
            'Referer': url,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) "
                          "Gecko/20100101 Firefox/143.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9"
        }

        response = session.get(url, headers=headers)

        if response.status_code != 200:
            self.logger.error(
                f"Ошибка при получении страницы sell orders: "
                f"{response.status_code} {response.reason}")
            if response.status_code == 429:
                raise TooManyRequestsError()

        return response

    def get_account_balance(self, session: requests.Session) -> list[int] | None:
        response = self.get_account_page(session)

        if response.status_code != 200:
            return None

        result = [0, 0, 0]

        soup = BeautifulSoup(response.content, "html.parser")
        account_rows = soup.findAll("div", class_="accountRow accountBalance")

        result[0] = float(account_rows[0].get_text(strip=True).replace(",", ".").split()[0])
        try:
            result[1] = float(account_rows[1].get_text(strip=True).replace(",", ".").split()[0])
        except IndexError:
            pass
        
        result[2] = result[0] + result[1]

        return result

    # region Market History
    @staticmethod
    @rate_limited(3)
    def _get_history_page_content(session: requests.Session, count: int, start: int):
        url = f'{Urls.HISTORY}/render/?count={count}&start={start}'

        for _ in range(4):
            page = session.get(url)
            if page.status_code == 200:
                result = json.loads(page.content)
                if not result.get("total_count", 0):
                    time.sleep(5)
                else:
                    return result
            else:
                time.sleep(20)

        raise Exception("Не удалось получить страницу market history")

    @staticmethod
    def _get_item_count(item_name: str) -> (str, int):
        parts = item_name.strip().split(maxsplit=1)
        if parts and parts[0].replace(",", "").isdigit():
            count = int(parts[0].replace(",", ""))
            base_name = parts[1].strip() if len(parts) > 1 else ""
            return base_name, count
        return item_name, 1

    def _aggregate_data(self, html_content: str, aggregated_data: dict) -> dict:
        document = BeautifulSoup(html_content, 'html.parser')
        rows = document.find_all("div", class_="market_listing_row")
        if not rows:
            raise Exception("Не получены элементы market history")

        for row in reversed(rows):
            game_element = row.find("span", class_="market_listing_game_name")
            item_element = row.find("span", class_="market_listing_item_name")
            price_element = row.find("span", class_="market_listing_price")
            gain_or_loss_element = row.find("div", class_="market_listing_gainorloss")

            if not (game_element and item_element and price_element and gain_or_loss_element):
                raise Exception("Не все элементы получены")

            game_name = game_element.text.strip()
            item_name = item_element.text.strip()
            gain_or_loss = gain_or_loss_element.text.strip()
            price_text = price_element.text.strip()

            price = float(price_text.replace(",", ".").split()[0])

            item_name, count = self._get_item_count(item_name)

            item_stats = aggregated_data[game_name][item_name]
            if gain_or_loss == "+":
                item_stats.total_bought += count
                item_stats.sum_bought = round(item_stats.sum_bought + price, 2)
            elif gain_or_loss == "-":
                item_stats.total_sold += count
                item_stats.sum_sold = round(item_stats.sum_sold + price, 2)
            else:
                raise Exception(f"Не найдено gain_or_loss")

        return aggregated_data

    def _collect_aggregated_market_history(
            self, session: requests.Session, aggregated_data: dict, processed_count: int = 0,
            count_per_request: int = 500
    ) -> (int, dict):
        page_content = self._get_history_page_content(session, 1, 0)
        total_count = page_content.get("total_count", 0)
        start_total_count = total_count
        total_new_count = total_count - processed_count
        if total_new_count <= 0:
            print("Нет новых записей для обработки")
            return start_total_count, aggregated_data

        start = total_new_count
        with tqdm(
                total=total_new_count, unit="order", ncols=Config.TQDM_CONSOLE_WIDTH, desc="Processing market history"
        ) as pbar:
            while True:
                new_count = min(count_per_request, start + start_total_count - total_count)
                if new_count <= 0:
                    break
                start = max(start - new_count, 0)

                page_content = self._get_history_page_content(session, new_count, start)
                html_content = page_content.get("results_html", "")
                total_count_now = page_content.get("total_count", 0)
                total_count_difference = total_count_now - total_count
                if total_count_difference:
                    total_count = total_count_now
                    start += total_count_difference
                    page_content = self._get_history_page_content(session, new_count, start)
                    html_content = page_content.get("results_html", "")

                if not html_content:
                    raise Exception("Не получен results_html")

                aggregated_data = self._aggregate_data(html_content, aggregated_data)

                pbar.update(new_count)

        return start_total_count, aggregated_data

    @staticmethod
    def _load_summarize_market_history(file_path: str) -> (int, dict):
        file_path = Path(file_path)
        aggregated_data = defaultdict(lambda: defaultdict(MarketItemStats))
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                processed_count = saved.get("processed_count", 0)
                old_data = saved.get("aggregated_data", {})
                for game_name, items in old_data.items():
                    for item_name, stats in items.items():
                        item_stats = aggregated_data[game_name][item_name]
                        item_stats.total_bought = stats.get("total_bought", 0)
                        item_stats.total_sold = stats.get("total_sold", 0)
                        item_stats.sum_bought = stats.get("sum_bought", 0.0)
                        item_stats.sum_sold = stats.get("sum_sold", 0.0)
        else:
            processed_count = 0

        return processed_count, aggregated_data

    @staticmethod
    def _save_summarize_market_history(file_path: str, aggregated_data: dict, processed_count: int) -> None:
        serializable_data = {}
        for game_name, items in aggregated_data.items():
            serializable_data[game_name] = {}
            for item_name, stats in items.items():
                serializable_data[game_name][item_name] = {
                    "total_bought": stats.total_bought,
                    "total_sold": stats.total_sold,
                    "sum_bought": stats.sum_bought,
                    "sum_sold": stats.sum_sold,
                    "quantity_difference": stats.quantity_difference,
                    "sum_difference": stats.sum_difference
                }

        save_object = {
            "processed_count": processed_count,
            "aggregated_data": serializable_data
        }

        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(save_object, f, ensure_ascii=False, indent=2)

        print(f"Json сохранён: {file_path}. Всего записей: {save_object['processed_count']}")

    def summarize_market_history(
            self, session: requests.Session,
            json_file_path: str = "data/market_history/summarize.json",
            excel_file_path: str = "data/market_history/summarize.xlsx",
    ) -> None:
        processed_count, aggregated_data = self._load_summarize_market_history(json_file_path)

        new_processed_count, aggregated_data = self._collect_aggregated_market_history(
            session, aggregated_data, processed_count)

        if new_processed_count:
            self._save_summarize_market_history(json_file_path, aggregated_data, new_processed_count)
            self.excel_maker.summarize_json_to_excel(json_file_path, excel_file_path)
    # endregion
