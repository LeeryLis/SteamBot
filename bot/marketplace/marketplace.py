from typing import Any

import requests
from tools import CustomTTLCache
from urllib.parse import quote

from tools.file_managers.item_manager import ItemManager
from tools.rate_limiter import rate_limited
from enums import Config, Urls
from tools import BasicLogger
from utils.web_utils import api_request


class Marketplace(BasicLogger):
    def __init__(self, app_id: int, context_id: int, currency: int) -> None:
        """
        :param app_id: ID игры
        :param context_id: ID контекста
        :param currency: валюта
        """
        super().__init__(
            logger_name=f"{self.__class__.__name__}{app_id}",
            dir_specify=str(app_id),
            file_name=f"{self.__class__.__name__}"
        )

        self.app_id = app_id
        self.context_id = context_id
        self.currency = currency

        self.item_manager = ItemManager(self.app_id)

        self.cache_sales_per_day_filename = f"data/sales_per_day_cache/{self.app_id}.dill"
        self.cache_sales_per_day = CustomTTLCache.load_cache(
            self.cache_sales_per_day_filename, maxsize=1000, ttl=24*60*60)

    def save_cache_sales_per_day(self):
        self.cache_sales_per_day.save_cache(self.cache_sales_per_day_filename)

    @rate_limited(6)
    def get_item_market_data(self, session: requests.Session, item_name: str) -> requests.Response | None:
        params = {
            "country": "RU",
            "language": "russian",
            "currency": self.currency,
            "item_nameid": self.item_manager.items.get(item_name)
        }
        response = api_request(
            session,
            "GET",
            Urls.MARKET_ITEM_ORDERS_HISTOGRAM,
            headers={
                "Referer": f"{Urls.MARKET}/listings/{self.app_id}/{item_name}"
            },
            params=params,
            logger=self.logger
        )

        market_data: dict[str, Any] = response.json()
        if market_data.get('sell_order_graph', None) and market_data.get('buy_order_graph', None):
            return response

        return None

    def get_sales_per_day(self, session: requests.Session, item_name: str) -> int | None:
        if item_name in self.cache_sales_per_day:
            return self.cache_sales_per_day[item_name]

        response = self.get_item_public_info(session, item_name)
        if response.status_code != 200:
            return None

        try:
            sales_per_day = int(response.json().get('volume').replace(",", ""))
            self.cache_sales_per_day[item_name] = sales_per_day
        except Exception:
            return 1

        return sales_per_day if sales_per_day > 0 else 1

    @rate_limited(6)
    def get_item_public_info(self, session: requests.Session, item_name: str) -> requests.Response:
        params = {
            "currency": self.currency,
            "appid": self.app_id,
            "market_hash_name": item_name
        }
        return api_request(
            session,
            "GET",
            Urls.MARKET_PRICE_OVERVIEW,
            headers={
                "Referer": f"{Urls.MARKET}/listings/{self.app_id}/{item_name}"
            },
            params=params,
            logger=self.logger
        )

    @rate_limited(1)
    def create_buy_order(
            self, session: requests.Session,
            item_name: str, price: float, quantity: int, confirmation_id: str = '0'
    ) -> requests.Response:
        data = {
            'sessionid': session.cookies.get("sessionid", domain="steamcommunity.com"),
            'currency': self.currency,
            'appid': self.app_id,
            'market_hash_name': item_name,
            'price_total': round(price * 100 * quantity),
            # 'tradefee_tax': 0,
            'quantity': quantity,
            # 'billing_state': '',
            # 'save_my_address': 0,
            'confirmation': confirmation_id
        }
        return api_request(
            session,
            "POST",
            f"{Urls.MARKET}/createbuyorder/",
            headers={
                "Referer": f"{Urls.MARKET}/listings/{self.app_id}/{quote(item_name)}"
            },
            data=data,
            logger=self.logger
        )

    @rate_limited(1)
    def create_sell_order(
            self, session: requests.Session, steam_id: str, asset_id: int, amount: int, price: float
    ) -> requests.Response:
        data = {
            'sessionid': session.cookies.get("sessionid", domain="steamcommunity.com"),
            'appid': self.app_id,
            'contextid': self.context_id,
            'assetid': asset_id,
            'amount': amount,
            'price': round(price * 100 * Config.WITH_COMMISSION)
        }
        return api_request(
            session,
            "POST",
            f"{Urls.MARKET}/sellitem/",
            headers={
                "Referer": f"https://steamcommunity.com/id/{steam_id}/inventory"
            },
            data=data,
            logger=self.logger
        )

    @rate_limited(1)
    def cancel_sell_order(self, session: requests.Session, sell_listing_id: int) -> requests.Response:
        data = {
            'sessionid': session.cookies.get("sessionid", domain="steamcommunity.com")
        }
        return api_request(
            session,
            "POST",
            f"{Urls.MARKET}/removelisting/{sell_listing_id}",
            headers={
                "Referer": Urls.MARKET
            },
            data=data,
            logger=self.logger
        )

    @rate_limited(1)
    def cancel_buy_order(self, session: requests.Session, buy_order_id: int) -> requests.Response:
        data = {
            'sessionid': session.cookies.get("sessionid", domain="steamcommunity.com"),
            'buy_orderid': buy_order_id
        }
        return api_request(
            session,
            "POST",
            f"{Urls.MARKET}/cancelbuyorder/",
            headers={
                "Referer": Urls.MARKET
            },
            data=data,
            logger=self.logger
        )
