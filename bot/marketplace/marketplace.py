from typing import Any

import os
import requests
import logging
from logging.handlers import RotatingFileHandler
from tools import CustomTTLCache

from utils import handle_status_codes_using_attempts
from tools.file_managers.item_manager import ItemManager
from tools.rate_limiter import BasicRateLimit, rate_limited_cls
from utils.exceptions import TooManyRequestsError
from enums import Config, Urls

from _root import project_root


class Marketplace(BasicRateLimit):
    def __init__(self, app_id: int, context_id: int, currency: int) -> None:
        """
        :param app_id: ID игры
        :param context_id: ID контекста
        :param currency: валюта
        """
        super().__init__()

        self.app_id = app_id
        self.context_id = context_id
        self.currency = currency

        self.item_manager = ItemManager(self.app_id)

        self.cache_sales_per_day_filename = f"data/sales_per_day_cache/{self.app_id}.dill"
        self.cache_sales_per_day = CustomTTLCache.load_cache(
            self.cache_sales_per_day_filename, maxsize=1000, ttl=7*24*60*60)

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

    def save_cache_sales_per_day(self):
        self.cache_sales_per_day.save_cache(self.cache_sales_per_day_filename)

    def set_service_limits(self):
        self.rate_limiter.set_limit(
            "itemordershistogram", 4
        )
        self.rate_limiter.set_limit(
            "priceoverview", 4
        )
        self.rate_limiter.set_limit(
            "createbuyorder", 0.5
        )
        self.rate_limiter.set_limit(
            "sellitem", 0.5
        )
        self.rate_limiter.set_limit(
            "removelisting", 0.5
        )
        self.rate_limiter.set_limit(
            "cancelbuyorder", 0.5
        )

    @handle_status_codes_using_attempts()
    @rate_limited_cls("itemordershistogram")
    def get_item_market_data(self, session: requests.Session, item_name: str) -> requests.Response | None:
        params = {
            "country": "RU",
            "language": "russian",
            "currency": self.currency,
            "item_nameid": self.item_manager.items.get(item_name)
        }
        headers = {
            'Referer': f'{Urls.MARKET}/listings/{self.app_id}/{item_name}',
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0 (Edition Yx 08)'
            ),
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

    @handle_status_codes_using_attempts()
    @rate_limited_cls("priceoverview")
    def get_item_public_info(self, session: requests.Session, item_name: str) -> requests.Response:
        params = {
            "currency": self.currency,
            "appid": self.app_id,
            "market_hash_name": item_name
        }
        headers = {
            'Referer': f'{Urls.MARKET}/listings/{self.app_id}/{item_name}',
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0 (Edition Yx 08)'
            ),
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
    @rate_limited_cls("createbuyorder")
    def create_buy_order(self, session: requests.Session, item_name: str, price: float, quantity: int) -> requests.Response:
        data = {
            'sessionid': session.cookies.get("sessionid", domain="steamcommunity.com"),
            'currency': self.currency,
            'appid': self.app_id,
            'market_hash_name': item_name,
            'price_total': round(price * 100 * quantity),
            'quantity': quantity
        }
        headers = {
            'Referer': f'{Urls.MARKET}/listings/{self.app_id}/{item_name}',
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0 (Edition Yx 08)'
            ),
            'Accept': '*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'X-Requested-With': 'XMLHttpRequest',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        }

        response = session.post(f'{Urls.MARKET}/createbuyorder/', data=data, headers=headers)

        if response.status_code != 200:
            self.logger.error(
                f"Ошибка при создании buy order '{item_name}': "
                f"{response.status_code} {response.reason}"
            )
            if response.status_code == 429:
                raise TooManyRequestsError()

        return response

    @handle_status_codes_using_attempts()
    @rate_limited_cls("sellitem")
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
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0 (Edition Yx 08)'
            ),
            'Host': "steamcommunity.com",
            'Referer': f'https://steamcommunity.com/id/{steam_id}/inventory',
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
    @rate_limited_cls("removelisting")
    def cancel_sell_order(self, session: requests.Session, sell_listing_id: int) -> requests.Response:
        url = f"https://steamcommunity.com/market/removelisting/{sell_listing_id}"
        data = {
            'sessionid': session.cookies.get("sessionid", domain="steamcommunity.com")
        }
        headers = {
            'Referer': "https://steamcommunity.com/market/",
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0 (Edition Yx 08)'
            ),
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
    @rate_limited_cls("cancelbuyorder")
    def cancel_buy_order(self, session: requests.Session, buy_order_id: int) -> requests.Response:
        url = "https://steamcommunity.com/market/cancelbuyorder/"
        headers = {
            'Referer': "https://steamcommunity.com/market/",
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0 (Edition Yx 08)'
            ),
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

