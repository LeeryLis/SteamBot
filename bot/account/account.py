import os
import re
import json
import time
import subprocess
from datetime import datetime, date

import requests
from tqdm import tqdm
from bs4 import BeautifulSoup
from collections import defaultdict

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions

from tools.rate_limiter import rate_limited
from tools import BasicLogger
from tools.file_store import FileStore, FileStoreType

from enums import Urls
from enums import Config
from bot.account.item_asset import ItemAsset
from bot.account.market_item_stats import MarketItemStats
from bot.account.market_month_stats import MarketMonthStats
from bot.account.summarize_to_excel import SummarizeToExcel
from utils.web_utils import api_request
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

        self.dates_file_path = "data/market_history/detailed/dates.json"

    @rate_limited(1)
    def get_account_page(self, session: requests.Session) -> requests.Response:
        return api_request(
            session,
            "GET",
            Urls.ACCOUNT,
            headers={
                "Referer": Urls.ACCOUNT
            },
            logger=self.logger
        )

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
    @rate_limited(3)
    def _get_history_page_content(
            self, session: requests.Session, count: int, start: int, max_attempts: int = 4) -> dict:
        for _ in range(max_attempts):
            try:
                page = api_request(
                    session,
                    "GET",
                    f"{Urls.HISTORY}/render/?count={count}&start={start}",
                    logger=self.logger
                )
                result = json.loads(page.content)
                if not result.get("total_count", 0):
                    time.sleep(5)
                else:
                    return result
            except TooManyRequestsError:
                time.sleep(20)

        raise RuntimeError("Не удалось получить страницу market history")

    @staticmethod
    def _build_hover_map(hovers: str) -> dict[str, ItemAsset]:
        hover_map: dict[str, ItemAsset] = {}

        re_call = re.compile(
            r"CreateItemHoverFromContainer\(\s*g_rgAssets\s*,\s*"
            r"(?P<quote1>['\"])(?P<container>.+?)(?P=quote1)\s*,\s*"
            r"(?P<app_id>\d+)\s*,\s*"
            r"(?P<quote2>['\"])(?P<context_id>.+?)(?P=quote2)\s*,\s*"
            r"(?P<quote3>['\"])(?P<item_id>\d+)(?P=quote3)\s*,\s*"
            r"(?P<rest>\d+)\s*\)",
            flags=re.IGNORECASE
        )

        for m in re_call.finditer(hovers):
            container = m.group("container")
            app_id = m.group("app_id")
            context_id = m.group("context_id")
            item_id = m.group("item_id")

            key = re.sub(r"_(name|image|icon|link|price|count)$", "", container, flags=re.IGNORECASE)

            if not hover_map.get(key):
                hover_map[key] = ItemAsset(app_id, context_id, item_id)

        return hover_map

    @staticmethod
    def _get_split_name_count(item_name: str) -> (str, int):
        parts = item_name.strip().split(maxsplit=1)
        if parts and parts[0].isdigit():
            count = int(parts[0])
            base_name = parts[1].strip() if len(parts) > 1 else ""
            return base_name, count
        return item_name, 1

    def _aggregate_data(
            self,
            page_content: dict,
            aggregated_data: dict,
            app_id_to_game_name: dict,
            unknown_prefix: str,
            monthly_aggregated_data: dict,
            full_dates: list[date],
            date_cursor: int
    ) -> (dict, dict, int):
        html_content: str = page_content.get("results_html", "")
        assets: dict = page_content.get("assets", "")
        hovers: str = page_content.get("hovers", "")

        if not (html_content and assets and hovers):
            raise Exception("Не получены элементы страницы истории")

        hover_map = self._build_hover_map(hovers)

        document = BeautifulSoup(html_content, 'html.parser')
        rows = document.find_all("div", class_="market_listing_row")
        if not rows:
            raise Exception("Не получены элементы market history")

        for row in reversed(rows):
            game_element = row.find("span", class_="market_listing_game_name")
            item_element = row.find("span", class_="market_listing_item_name")
            price_element = row.find("span", class_="market_listing_price")
            gain_or_loss_element = row.find("div", class_="market_listing_gainorloss")
            date_element = row.find("div", class_="market_listing_listed_date")
            history_row_id = row.get("id")

            if not (game_element and item_element and price_element and gain_or_loss_element and date_element):
                raise Exception("Не все элементы получены")

            asset: ItemAsset = hover_map.get(history_row_id)
            item: dict = assets[asset.AppID][asset.ContextID][asset.ItemID]

            game_name = game_element.text.strip()
            gain_or_loss = gain_or_loss_element.text.strip()
            price_text = price_element.text.strip()
            price = float(price_text.replace(",", ".").split()[0])

            item_hash_name = item.get("market_hash_name")
            if not item_hash_name:
                item_hash_name = f"unknown_{unknown_prefix}_id={asset.ItemID}"
            _, count = self._get_split_name_count(item_element.text.strip())

            history_date = self._parse_partial_date(date_element.text.strip())
            actual_date, date_cursor = self._get_actual_month_year(full_dates, date_cursor, history_date)

            month_stats: MarketMonthStats = monthly_aggregated_data[asset.AppID][actual_date]
            if gain_or_loss == "+":
                month_stats.total_bought += count
                month_stats.sum_bought = round(month_stats.sum_bought + price, 2)
            elif gain_or_loss == "-":
                month_stats.total_sold += count
                month_stats.sum_sold = round(month_stats.sum_sold + price, 2)
            else:
                raise Exception(f"Не найдено gain_or_loss")

            item_stats: MarketItemStats = aggregated_data[asset.AppID][item_hash_name]
            item_stats.item_name = item.get("market_name")
            if not item_stats.item_name:
                item_stats.item_name = f"unknown_{asset.AppID}_{asset.ItemID}"
            if gain_or_loss == "+":
                item_stats.total_bought += count
                item_stats.sum_bought = round(item_stats.sum_bought + price, 2)
            elif gain_or_loss == "-":
                item_stats.total_sold += count
                item_stats.sum_sold = round(item_stats.sum_sold + price, 2)
            else:
                raise Exception(f"Не найдено gain_or_loss")

            if not app_id_to_game_name.get(asset.AppID):
                if asset.AppID == '753':
                    app_id_to_game_name[asset.AppID] = "Steam"
                else:
                    app_id_to_game_name[asset.AppID] = game_name

        return aggregated_data, app_id_to_game_name, date_cursor

    def _collect_aggregated_market_history(
            self, session: requests.Session,
            aggregated_data: dict,
            app_id_to_game_name: dict,
            monthly_aggregated_data: dict,
            full_dates: list[date],
            date_cursor: int,
            processed_count: int = 0,
            count_per_request: int = 500
    ) -> (int, dict, dict, dict):
        page_content = self._get_history_page_content(session, 1, 0)
        total_count = page_content.get("total_count", 0)
        start_total_count = total_count
        total_new_count = total_count - processed_count
        if total_new_count <= 0:
            print("Нет новых записей для обработки")
            return start_total_count, aggregated_data, monthly_aggregated_data, app_id_to_game_name

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
                total_count_now = page_content.get("total_count", 0)
                total_count_difference = total_count_now - total_count
                if total_count_difference:
                    total_count = total_count_now
                    start += total_count_difference
                    page_content = self._get_history_page_content(session, new_count, start)

                aggregated_data, app_id_to_game_name, date_cursor = self._aggregate_data(
                    page_content, aggregated_data, app_id_to_game_name,
                    f"start={start}_count={new_count}_total={total_count}",
                    monthly_aggregated_data, full_dates, date_cursor
                )

                pbar.update(new_count)

        return start_total_count, aggregated_data, monthly_aggregated_data, app_id_to_game_name

    @staticmethod
    def _load_summarize_market_history(file_path: str) -> (int, dict, dict):
        processed_count = 0
        aggregated_data = defaultdict(lambda: defaultdict(MarketItemStats))
        app_id_to_game_name = {}

        file_store = FileStore.from_type(FileStoreType.JSON)
        saved = file_store.load(file_path, default=None)

        if saved:
            processed_count = saved.get("processed_count", 0)
            old_data = saved.get("aggregated_data", {})
            app_id_to_game_name = saved.get("app_id_to_game_name", {})

            for game_name, items in old_data.items():
                for item_name, stats in items.items():
                    item_stats = aggregated_data[game_name][item_name]
                    item_stats.item_name = stats.get("item_name", "")
                    item_stats.total_bought = stats.get("total_bought", 0)
                    item_stats.total_sold = stats.get("total_sold", 0)
                    item_stats.sum_bought = stats.get("sum_bought", 0.0)
                    item_stats.sum_sold = stats.get("sum_sold", 0.0)

        return processed_count, aggregated_data, app_id_to_game_name

    @staticmethod
    def _load_monthly_summarize_market_history(file_path: str) -> (dict, dict):
        aggregated_data = defaultdict(lambda: defaultdict(MarketMonthStats))
        app_id_to_game_name = {}

        file_store = FileStore.from_type(FileStoreType.JSON)
        saved = file_store.load(file_path, default=None)

        if saved:
            old_data = saved.get("aggregated_data", {})
            app_id_to_game_name = saved.get("app_id_to_game_name", {})

            for game_name, items in old_data.items():
                for actual_date, stats in items.items():
                    month_stats = aggregated_data[game_name][actual_date]
                    month_stats.total_bought = stats.get("total_bought", 0)
                    month_stats.total_sold = stats.get("total_sold", 0)
                    month_stats.sum_bought = stats.get("sum_bought", 0.0)
                    month_stats.sum_sold = stats.get("sum_sold", 0.0)

        return aggregated_data, app_id_to_game_name

    @staticmethod
    def _save_summarize_market_history(
            file_path: str,
            aggregated_data: dict,
            app_id_to_game_name: dict,
            processed_count: int
    ) -> None:
        serializable_data = {}
        for game_name, items in aggregated_data.items():
            serializable_data[game_name] = {}
            for item_name, stats in items.items():
                serializable_data[game_name][item_name] = {
                    "item_name": stats.item_name,
                    "total_bought": stats.total_bought,
                    "total_sold": stats.total_sold,
                    "sum_bought": stats.sum_bought,
                    "sum_sold": stats.sum_sold,
                    "quantity_difference": stats.quantity_difference,
                    "sum_difference": stats.sum_difference
                }

        save_object = {
            "processed_count": processed_count,
            "app_id_to_game_name": app_id_to_game_name,
            "aggregated_data": serializable_data
        }

        file_store = FileStore.from_type(FileStoreType.JSON)
        file_store.save(file_path, save_object)
        print(f"Json сохранён: {file_path}. Всего записей: {save_object['processed_count']}")

    @staticmethod
    def _save_monthly_summarize_market_history(
            file_path: str,
            aggregated_data: dict,
            app_id_to_game_name: dict
    ) -> None:
        serializable_data = {}
        for game_name, items in aggregated_data.items():
            serializable_data[game_name] = {}
            for actual_date, stats in items.items():
                serializable_data[game_name][actual_date] = {
                    "total_bought": stats.total_bought,
                    "total_sold": stats.total_sold,
                    "sum_bought": stats.sum_bought,
                    "sum_sold": stats.sum_sold,
                    "quantity_difference": stats.quantity_difference,
                    "sum_difference": stats.sum_difference
                }

        save_object = {
            "app_id_to_game_name": app_id_to_game_name,
            "aggregated_data": serializable_data
        }

        file_store = FileStore.from_type(FileStoreType.JSON)
        file_store.save(file_path, save_object)
        print(f"Json сохранён: {file_path}")

    def summarize_market_history(
            self, session: requests.Session,
            json_file_path: str = "data/market_history/summarize.json",
            excel_file_path: str = "data/market_history/summarize.xlsx",
            monthly_json_file_path: str = "data/market_history/detailed/monthly_summarize.json",
            monthly_excel_file_path: str = "data/market_history/detailed/monthly_summarize.xlsx",
    ) -> None:
        full_dates, date_cursor = self._collect_history_dates(session)
        if date_cursor > 0:
            date_cursor -= 1
        processed_count, aggregated_data, app_id_to_game_name = self._load_summarize_market_history(json_file_path)
        monthly_aggregated_data, _ = self._load_monthly_summarize_market_history(monthly_json_file_path)

        try:
            new_processed_count, aggregated_data, monthly_aggregated_data, app_id_to_game_name = \
                self._collect_aggregated_market_history(
                    session, aggregated_data, app_id_to_game_name, monthly_aggregated_data,
                    full_dates, date_cursor, processed_count
                )
        except RuntimeError as e:
            print("Ошибка:", e)
            return

        if new_processed_count - processed_count > 0:
            self._save_summarize_market_history(
                json_file_path, aggregated_data, app_id_to_game_name, new_processed_count)
            self._save_monthly_summarize_market_history(
                monthly_json_file_path, monthly_aggregated_data, app_id_to_game_name)
        try:
            self.excel_maker.summarize_json_to_excel(json_file_path, excel_file_path)
            self.excel_maker.monthly_summarize_json_to_excel(monthly_json_file_path, monthly_excel_file_path)
        except Exception as e:
            print("Ошибка:", e)
    # endregion

    # region dates
    @staticmethod
    def _parse_partial_date(partial: str) -> date:
        day, month_str = partial.split()
        month = datetime.strptime(month_str, "%b").month
        return date(1904, month, int(day))

    @staticmethod
    def _month_key(d: date) -> str:
        return d.strftime("%m.%Y")

    def _get_actual_month_year(self, full_dates: list[date], date_cursor: int, history_date: date) -> (date, int):
        picked_date = full_dates[date_cursor]
        if history_date.month == picked_date.month and history_date.day == picked_date.day:
            return self._month_key(picked_date), date_cursor

        date_cursor -= 1
        next_picked_date = full_dates[date_cursor]
        if history_date.month != next_picked_date.month or history_date.day != next_picked_date.day:
            date_cursor += 1
            next_picked_date = date(picked_date.year, history_date.month, history_date.day)
            full_dates.insert(date_cursor, next_picked_date)
            # print(f"\nДобавлена дата {next_picked_date}")
            # raise RuntimeError(f"Не совпали даты: {history_date} != {picked_date}")
        return self._month_key(next_picked_date), date_cursor

    def _collect_history_dates(self, session: requests.Session) -> (list[date], int):
        all_dates = self._load_dates_from_file()
        if all_dates is None:
            return self._get_full_wallet_history(session)

        response = api_request(
            session,
            "GET",
            "https://store.steampowered.com/account/history/",
            headers={
                "Host": "store.steampowered.com",
                "Referer": Urls.ACCOUNT
            },
            logger=self.logger
        )

        if not self._is_able_to_continue_dates(all_dates, response.text):
            return self._get_full_wallet_history(session, all_dates)

        all_dates, new_dates_count = self._parse_dates(response.text, all_dates)

        self._save_dates_to_file(all_dates)

        return all_dates, new_dates_count

    def _is_able_to_continue_dates(self, all_dates: list[date], response_html: str) -> bool:
        last_date = all_dates[0]

        soup = BeautifulSoup(response_html, "html.parser")
        rows = soup.select("tr.wallet_table_row")

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue

            date_str = cols[0].get_text(strip=True)
            type_ = cols[2].get_text(strip=True)

            if not ("TransactionWallet" in type_ or "TransactionsWallet" in type_):
                continue

            parsed_date = self._parse_steam_date(date_str)
            if parsed_date == last_date:
                return True

        return False

    @staticmethod
    def _parse_steam_date(date_str: str) -> date:
        return datetime.strptime(date_str, "%d %b, %Y").date()

    def _parse_dates(self, response_html: str, dates: list = None) -> (list[date], int):
        if not dates:
            dates = []
        new_dates = []

        soup = BeautifulSoup(response_html, "html.parser")
        rows = soup.select("tr.wallet_table_row")

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 3:
                continue

            date_str = cols[0].get_text(strip=True)
            type_ = cols[2].get_text(strip=True)

            if not ("TransactionWallet" in type_ or "TransactionsWallet" in type_):
                continue

            if (parsed_date := self._parse_steam_date(date_str)) not in dates:
                if parsed_date in new_dates:
                    continue
                new_dates.append(parsed_date)
            else:
                break

        new_dates_count = len(new_dates)
        new_dates.extend(dates)
        return new_dates, new_dates_count

    def _save_dates_to_file(self, dates: list[date]) -> None:
        file_store = FileStore.from_type(FileStoreType.JSON)
        file_store.save(self.dates_file_path, [d.isoformat() for d in dates])

    def _load_dates_from_file(self) -> list[date] | None:
        try:
            with open(self.dates_file_path, "r", encoding="utf-8") as f:
                return [date.fromisoformat(d) for d in json.load(f)]
        except FileNotFoundError:
            return None

    @staticmethod
    def _load_cookies_into_selenium(driver: webdriver.Chrome, session: requests.Session):
        domain = "store.steampowered.com"
        driver.get(f"https://{domain}")
        for cookie in session.cookies:
            if cookie.domain == domain:
                cookie_dict = {
                    'name': cookie.name,
                    'value': cookie.value,
                    'domain': cookie.domain,
                    'path': cookie.path or '/',
                    'secure': cookie.secure,
                }
                if cookie.expires:
                    cookie_dict['expiry'] = int(cookie.expires)
                try:
                    driver.add_cookie(cookie_dict)
                except Exception as e:
                    print(f"Не удалось добавить куки {cookie.name}: {e}")

        driver.refresh()

    def _get_full_wallet_history(self, session: requests.Session, all_dates: list[date] = None) -> (list[date], int):
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--window-size=1200,800")
        options.add_argument("--log-level=3")
        options.add_argument("--disable-logging")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-features=SameSiteByDefaultCookies,BlockThirdPartyCookies")
        options.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")

        service = Service(log_output=os.devnull)
        try:
            service.creation_flags = subprocess.CREATE_NO_WINDOW
        except Exception:
            pass

        with webdriver.Chrome(service=service, options=options) as driver:
            self._load_cookies_into_selenium(driver, session)

            driver.get("https://store.steampowered.com/account/history/")

            while True:
                WebDriverWait(driver, 10).until(
                    expected_conditions.presence_of_element_located((By.CSS_SELECTOR, "tr.wallet_table_row"))
                )

                try:
                    load_more = driver.find_element(By.ID, "load_more_button")
                    if load_more.is_displayed():
                        load_more.click()
                        WebDriverWait(driver, 10).until(
                            expected_conditions.presence_of_element_located((By.ID, "load_more_button"))
                        )
                        if self._is_able_to_continue_dates(all_dates, driver.page_source):
                            break
                    else:
                        break
                except:
                    break

            all_dates, new_dates_count = self._parse_dates(driver.page_source, all_dates)

        self._save_dates_to_file(all_dates)

        return all_dates, new_dates_count
    # endregion
