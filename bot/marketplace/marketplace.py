import time
from typing import Any

import requests
from tools import CustomTTLCache
from urllib.parse import quote

from utils import handle_status_codes_using_attempts
from tools.file_managers.item_manager import ItemManager
from tools.rate_limiter import rate_limited
from utils.exceptions import TooManyRequestsError
from enums import Config, Urls
from tools import BasicLogger


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
        headers = {
            'Referer': f'{Urls.MARKET}/listings/{self.app_id}/{item_name}',
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) "
                          "Gecko/20100101 Firefox/143.0",
            'Accept': '*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'X-Requested-With': 'XMLHttpRequest',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        }
        url = f'{Urls.MARKET}/itemordershistogram'

        response = session.get(url, params=params, headers=headers)

        if response.status_code != 200:
            self.logger.error(
                f"Ошибка при получении данных торговой площадки для '{item_name}': "
                f"{response.status_code} {response.reason}"
            )
            if response.status_code == 429:
                raise TooManyRequestsError()

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
        headers = {
            'Referer': f'{Urls.MARKET}/listings/{self.app_id}/{item_name}',
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) "
                          "Gecko/20100101 Firefox/143.0",
            'Accept': '*/*',
            'Accept-Language': 'en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'X-Requested-With': 'XMLHttpRequest',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        }
        url = f"{Urls.MARKET}/priceoverview"

        response = session.get(url, params=params, headers=headers)

        if response.status_code != 200:
            self.logger.error(
                f"Ошибка при получении публичных данных для '{item_name}': "
                f"{response.status_code} {response.reason}")
            if response.status_code == 429:
                raise TooManyRequestsError()

        return response

    @handle_status_codes_using_attempts()
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
        headers = {
            'Referer': f'{Urls.MARKET}/listings/{self.app_id}/{quote(item_name)}'
        }
        response = session.post(
            url=f'{Urls.MARKET}/createbuyorder/', data=data, headers=headers)

        if response.status_code not in (200, 406):
            self.logger.error(
                f"Ошибка при создании buy order '{item_name}': "
                f"{response.status_code} {response.reason}"
            )
            if response.status_code == 429:
                raise TooManyRequestsError()

        return response

    @handle_status_codes_using_attempts()
    @rate_limited(1)
    def create_sell_order(self, session: requests.Session, steam_id: str, asset_id: int, amount: int, price: float) -> requests.Response:
        data = {
            'sessionid': session.cookies.get("sessionid", domain="steamcommunity.com"),
            'appid': self.app_id,
            'contextid': self.context_id,
            'assetid': asset_id,
            'amount': amount,
            'price': round(price * 100 * Config.WITH_COMMISSION)
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) "
                          "Gecko/20100101 Firefox/143.0",
            'Host': "steamcommunity.com",
            'Referer': f'https://steamcommunity.com/id/{steam_id}/inventory',
            # 'Referer': f'https://steamcommunity.com/profiles/{steam_id}/inventory',
            'Origin': 'https://steamcommunity.com',
            'Accept': '*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'X-Requested-With': 'XMLHttpRequest',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        }

        response = session.post(f'{Urls.MARKET}/sellitem/', data=data, headers=headers)

        if response.status_code != 200:
            self.logger.error(
                f"Ошибка при создании sell order (asset_id = {asset_id}): "
                f"{response.status_code} {response.reason}"
            )
            if response.status_code == 429:
                raise TooManyRequestsError()

        return response

    @handle_status_codes_using_attempts()
    @rate_limited(1)
    def cancel_sell_order(self, session: requests.Session, sell_listing_id: int) -> requests.Response:
        url = f"https://steamcommunity.com/market/removelisting/{sell_listing_id}"
        data = {
            'sessionid': session.cookies.get("sessionid", domain="steamcommunity.com")
        }
        headers = {
            'Referer': "https://steamcommunity.com/market/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) "
                          "Gecko/20100101 Firefox/143.0",
            'Accept': '*/*'
        }

        response = session.post(url, data=data, headers=headers)

        if response.status_code != 200:
            self.logger.error(
                f"Ошибка при отмене sell order (sell_listing_id = {sell_listing_id}): "
                f"{response.status_code} {response.reason}"
            )
            if response.status_code == 429:
                raise TooManyRequestsError()

        return response

    @handle_status_codes_using_attempts()
    @rate_limited(1)
    def cancel_buy_order(self, session: requests.Session, buy_order_id: int) -> requests.Response:
        url = "https://steamcommunity.com/market/cancelbuyorder/"
        headers = {
            'Referer': "https://steamcommunity.com/market/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) "
                          "Gecko/20100101 Firefox/143.0",
            'Accept': '*/*'
        }
        data = {
            'sessionid': session.cookies.get("sessionid", domain="steamcommunity.com"),
            'buy_orderid': buy_order_id
        }

        response = session.post(url, headers=headers, data=data)

        if response.status_code != 200:
            self.logger.error(
                f"Ошибка при отмене buy order (buy_order_id = {buy_order_id}): "
                f"{response.status_code} {response.reason}"
            )
            if response.status_code == 429:
                raise TooManyRequestsError()

        return response
