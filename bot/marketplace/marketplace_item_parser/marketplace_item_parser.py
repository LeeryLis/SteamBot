import re

import os
import bs4.element
import requests
from bs4 import BeautifulSoup
import urllib.parse
import logging
from logging.handlers import RotatingFileHandler

from utils import handle_status_codes_using_attempts
from tools.rate_limiter import BasicRateLimit, rate_limited_cls
from bot.marketplace.marketplace_item_parser.sell_order_item import SellOrderItem
from bot.marketplace.marketplace_item_parser.buy_order_item import BuyOrderItem
from utils.exceptions import TooManyRequestsError
from enums import Urls

from _root import project_root


class MarketplaceItemParser(BasicRateLimit):
    def __init__(self, app_id: int, context_id: int) -> None:
        """
        :param app_id: ID игры
        :param context_id: ID контекста
        """
        super().__init__()

        self.app_id = app_id
        self.context_id = context_id

        self.sell_orders: dict[str, list[SellOrderItem]] = {}
        self.buy_orders: dict[str, BuyOrderItem] = {}

        self.logger = logging.getLogger(f"{self.__class__.__name__}{self.app_id}")
        if not self.logger.handlers:
            file_path = f"{project_root}/logs/{self.app_id}/{self.__class__.__name__}.log"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            handler = RotatingFileHandler(
                file_path,
                encoding="utf-8",
                maxBytes=1024 * 1024,
                backupCount=5
            )
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)

    def set_service_limits(self):
        self.rate_limiter.set_limit(
            "mylistings", 1
        )
        self.rate_limiter.set_limit(
            "listings", 3
        )
        self.rate_limiter.set_limit(
            "market_buy_orders", 3
        )

    @handle_status_codes_using_attempts()
    @rate_limited_cls("mylistings")
    def get_sell_orders_page(self, session: requests.Session, is_check_connection: bool = False) -> requests.Response:
        url = f"{Urls.MARKET}/mylistings/render/?query=&start=0&count=-1"
        headers = {
            'Accept': 'text/javascript, text/html, application/xml, text/xml, */*',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'Accept-Language': 'en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'Host': 'steamcommunity.com',
            'Referer': f'{Urls.MARKET}',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0 (Edition Yx 08)'
            ),
            'X-Prototype-Version': '1.7',
            'X-Requested-With': 'XMLHttpRequest',
        }

        response = session.get(url, headers=headers)

        if response.status_code != 200 and not is_check_connection:
            self.logger.error(
                f"Ошибка при получении страницы sell orders: "
                f"{response.status_code} {response.reason}")
            if response.status_code == 429:
                raise TooManyRequestsError()

        return response

    @handle_status_codes_using_attempts()
    @rate_limited_cls("market_buy_orders")
    def _get_buy_orders_page(self, session: requests.Session) -> requests.Response:
        url = f"{Urls.MARKET}"
        headers = {
            'Referer': url,
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0 (Edition Yx 08)'
            ),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,'
                      '*/*;q=0.8,application/signed-exchange;v=b3;q=0.7'
        }

        response = session.get(url, headers=headers, cookies=session.cookies)

        if response.status_code != 200:
            self.logger.error(
                f"Ошибка при получении страницы маркета всех бай ордеров: "
                f"{response.status_code} {response.reason}")
            if response.status_code == 429:
                raise TooManyRequestsError()

        return response

    def _get_item_app_id_sell_order(self, element: bs4.element.Tag) -> int:
        remove_button_link = element.find(
            "a",
            class_="item_market_action_button item_market_action_button_edit nodisable")
        remove_button_href = remove_button_link.get("href", "")
        return int(re.search(r"RemoveMarketListing\('mylisting', '\d+', (\d+),", remove_button_href).group(1))

    def _get_item_app_id_buy_order(self, element: bs4.element.Tag) -> int:
        item_page_link = element.find(
            "a",
            class_="market_listing_item_name_link")
        name_href = item_page_link.get("href", "")
        return int(re.search(r"https://steamcommunity.com/market/listings/(\d+)", name_href).group(1))

    def parse_actual_sell_order_items(self, session: requests.Session) -> dict[str, list[SellOrderItem]] | None:
        response = self.get_sell_orders_page(session)

        if response.status_code != 200:
            return None

        data = response.json()
        html_content = data["results_html"]

        sell_order_items = []

        for _, asset_info in data.get("assets", {}).get(str(self.app_id), {}).get(str(self.context_id), {}).items():
            item = SellOrderItem(app_id=self.app_id, context_id=self.context_id)
            item.name = asset_info["market_hash_name"]
            sell_order_items.append(item)

        soup = BeautifulSoup(html_content, "html.parser")

        i = 0
        for element in soup.find_all("div", class_="market_listing_row"):
            app_id = self._get_item_app_id_sell_order(element)
            if app_id != self.app_id:
                continue

            order_id = int(element.get("id", "").split("_")[1])
            sell_order_items[i].order_id = order_id

            buyer_price = element.find("span", title="This is the price the buyer pays.")
            seller_price = element.find("span", title="This is how much you will receive.")
            creation_date = element.find("div",
                                         class_="market_listing_right_cell market_listing_listed_date can_combine")

            sell_order_items[i].buyer_price = float(
                buyer_price.get_text(strip=True).replace(",", ".").split()[0] if buyer_price else None
            )
            sell_order_items[i].seller_price = float(
                seller_price.get_text(strip=True).replace(",", ".").replace("(", "").replace(")", "").split()[0] \
                    if seller_price else None
            )
            sell_order_items[i].creation_date = creation_date.get_text(strip=True) if creation_date else None

            i += 1

        self.sell_orders = {}
        for item in sell_order_items:
            if not self.sell_orders.get(item.name):
                self.sell_orders[item.name] = []
            self.sell_orders[item.name].append(item)

        return self.sell_orders

    def parse_actual_buy_order_items(self, session: requests.Session) -> dict[str, BuyOrderItem] | None:
        self.buy_orders = {}

        response = self._get_buy_orders_page(session)

        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        raw_buy_orders = soup.find_all(
            "div", class_="market_listing_row market_recent_listing_row")

        for raw_buy_order in raw_buy_orders:
            app_id = self._get_item_app_id_buy_order(raw_buy_order)

            if not app_id == self.app_id:
                continue

            item_name = raw_buy_order.find(
                "a",
                class_="market_listing_item_name_link").text

            buy_order_item = BuyOrderItem(app_id=self.app_id, context_id=self.context_id, name=item_name)
            buy_order_item.order_id = raw_buy_order.get("id").split("_")[1]

            price: str = raw_buy_order.find("span", class_="market_listing_price").text
            price = price.split('@')[1].strip()
            quantity: str = raw_buy_order.find("span", class_="market_listing_inline_buyorder_qty").text

            buy_order_item.price = float(price.replace(",", ".").strip().split()[0])
            buy_order_item.quantity = int(quantity.replace("@", "").strip())

            self.buy_orders[item_name] = buy_order_item

        return self.buy_orders
