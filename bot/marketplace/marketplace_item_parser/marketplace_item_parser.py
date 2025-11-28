import re

import bs4.element
import requests
from bs4 import BeautifulSoup

from tools.rate_limiter import rate_limited
from bot.marketplace.marketplace_item_parser.sell_order_item import SellOrderItem
from bot.marketplace.marketplace_item_parser.buy_order_item import BuyOrderItem
from enums import Urls
from tools import BasicLogger
from utils.web_utils import api_request


class MarketplaceItemParser(BasicLogger):
    def __init__(self, app_id: int, context_id: int) -> None:
        """
        :param app_id: ID игры
        :param context_id: ID контекста
        """
        super().__init__(
            logger_name=f"{self.__class__.__name__}{app_id}",
            dir_specify=str(app_id),
            file_name=f"{self.__class__.__name__}"
        )

        self.app_id = app_id
        self.context_id = context_id

        self.sell_orders: dict[str, list[SellOrderItem]] = {}
        self.buy_orders: dict[str, BuyOrderItem] = {}

    @rate_limited(6)
    def get_sell_orders_page(self, session: requests.Session) -> requests.Response:
        return api_request(
            session,
            "GET",
            f"{Urls.MARKET}/mylistings/render/?query=&start=0&count=-1",
            headers={
                "Referer": Urls.MARKET,
            },
            logger=self.logger
        )

    @rate_limited(6)
    def _get_buy_orders_page(self, session: requests.Session) -> requests.Response:
        return api_request(
            session,
            "GET",
            Urls.MARKET,
            headers={
                "Referer": Urls.MARKET
            },
            logger=self.logger
        )

    @staticmethod
    def _get_item_app_id_sell_order(element: bs4.element.Tag) -> int:
        remove_button_link = element.find(
            "a",
            class_="item_market_action_button item_market_action_button_edit nodisable")
        remove_button_href = remove_button_link.get("href", "")
        return int(re.search(r"RemoveMarketListing\('mylisting', '\d+', (\d+),", remove_button_href).group(1))

    @staticmethod
    def _get_item_app_id_buy_order(element: bs4.element.Tag) -> int:
        item_page_link = element.find(
            "a",
            class_="market_listing_item_name_link")
        name_href = item_page_link.get("href", "")
        return int(re.search(r"https://steamcommunity.com/market/listings/(\d+)", name_href).group(1))

    @staticmethod
    def _get_item_count(element: bs4.element.Tag) -> int:
        market_listing_item_name_link = element.find(
            "a",
            class_="market_listing_item_name_link")
        name_text = market_listing_item_name_link.text
        count = name_text.split(" ")[0].replace(",", "")
        if str.isdigit(count):
            return int(count)
        return 1

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
            try:
                sell_order_items[i].order_id = order_id
            except IndexError:
                break

            buyer_price = element.find("span", title="This is the price the buyer pays.")
            seller_price = element.find("span", title="This is how much you will receive.")
            creation_date = element.find("div",
                                         class_="market_listing_right_cell market_listing_listed_date can_combine")

            count = self._get_item_count(element)
            sell_order_items[i].count = count

            sell_order_items[i].buyer_price = count * float(
                buyer_price.get_text(strip=True).replace(",", ".").split()[0] if buyer_price else None
            )
            sell_order_items[i].seller_price = count * float(
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
