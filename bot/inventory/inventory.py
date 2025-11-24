import os
import requests

from bot.inventory.inventory_item import InventoryItem
from tools.rate_limiter import rate_limited
from utils import handle_status_codes_using_attempts
from tools import BasicLogger

from enums import Urls


class Inventory(BasicLogger):
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

    @handle_status_codes_using_attempts()
    @rate_limited(2)
    def get_inventory_page(
            self, session: requests.Session, count: int, start_asset_id: str = None
    ) -> requests.Response:
        url = f"{Urls.INVENTORY}/{os.getenv('STEAM_ID')}/{self.app_id}/{self.context_id}"
        params = {
            "l": "english",  # Язык ответа
            "count": count,  # Максимальное количество предметов за один запрос
            "start_assetid": start_asset_id  # Последний полученный id при последовательном получении большого инвентаря
        }

        response = session.get(url, params=params)

        if response.status_code != 200:
            self.logger.error(
                f"Ошибка при получении инвентаря: "
                f"{response.status_code} {response.reason}")

        return response

    def get_inventory(self, session: requests.Session, count_const: int = 1000) -> list[requests.Response] | None:
        result = []
        last_assetid = None
        while True:
            response = self.get_inventory_page(session, count_const, last_assetid)
            if response.status_code != 200:
                return None
            result.append(response)

            last_assetid = response.json().get('last_assetid', None)
            if not last_assetid:
                break

        return result

    def get_inventory_items(self, session: requests.Session) -> dict[str, InventoryItem]:
        response_list = self.get_inventory(session)

        if not response_list:
            return {}

        descriptions = []
        assets = []
        for response in response_list:
            data = response.json()
            descriptions.extend(data.get('descriptions', []))
            assets.extend(data.get('assets', []))

        inventory_items = {}

        for description in descriptions:
            key = description.get('classid') + ";" + description.get('instanceid')
            if key not in inventory_items:
                item = InventoryItem(
                    description.get('market_hash_name'),
                    description.get('marketable'),
                    'owner_descriptions' in description
                )
                inventory_items[key] = item

        for asset in assets:
            key = asset.get('classid') + ";" + asset.get('instanceid')
            if key in inventory_items:
                inventory_items[key].add_asset_id(int(asset.get('assetid')))

        return inventory_items
