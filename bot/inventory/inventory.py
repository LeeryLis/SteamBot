import os
import requests
import logging
from logging.handlers import RotatingFileHandler

from bot.inventory.inventory_item import InventoryItem
from tools.rate_limiter import BasicRateLimit, rate_limited_cls
from utils import handle_status_codes_using_attempts

from enums import Urls

from _root import project_root


class Inventory(BasicRateLimit):
    def __init__(self, steam_id: int | str, app_id: int, context_id: int) -> None:
        """
        :param steam_id: ID аккаунта Steam
        :param app_id: ID игры
        :param context_id: ID контекста
        """
        super().__init__()

        self.steam_id = steam_id
        self.app_id = app_id
        self.context_id = context_id

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
            "inventory", 1
        )

    @handle_status_codes_using_attempts(3)
    @rate_limited_cls("inventory")
    def get_inventory(self, session: requests.Session) -> requests.Response:
        url = f"{Urls.INVENTORY}/{self.steam_id}/{self.app_id}/{self.context_id}"
        params = {
            "l": "english",  # Язык ответа
            "count": 5000  # Максимальное количество предметов за один запрос
        }

        response = session.get(url, params=params)

        if response.status_code != 200:
            self.logger.error(
                f"Ошибка при получении инвентаря: "
                f"{response.status_code} {response.reason}")

        return response

    def get_inventory_items(self, session: requests.Session) -> dict[str, InventoryItem]:
        response = self.get_inventory(session)

        if response.status_code != 200:
            return {}

        data = response.json()
        descriptions = data.get('descriptions', [])
        assets = data.get('assets', [])

        inventory_items = {}

        for description in descriptions:
            key = description.get('classid') + ";" + description.get('instanceid')

            if key not in inventory_items:
                item = InventoryItem(description.get('market_hash_name'), description.get('marketable'))
                inventory_items[key] = item

        for asset in assets:
            key = asset.get('classid') + ";" + asset.get('instanceid')
            if key in inventory_items:
                inventory_items[key].add_asset_id(int(asset.get('assetid')))

        return inventory_items
