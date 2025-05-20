import os
import logging
from logging.handlers import RotatingFileHandler

import requests
from tqdm import tqdm

from bot.inventory import Inventory, InventoryItem
from bot.marketplace import Marketplace
from bot.price_analysis import PriceAnalysis
from tools.file_managers import TradeItemManager
from bot.marketplace import MarketplaceItemParser

from _root import project_root


class InventorySeller:
    def __init__(
            self,
            steam_id: str,
            app_id: int,
            context_id: int,
            currency: int,
            marketplace: Marketplace
    ) -> None:
        """
        :param steam_id: id пользователя Steam
        :param app_id: ID игры
        :param context_id: ID контекста
        :param currency: валюта
        """
        self.steam_id = steam_id

        self.app_id = app_id
        self.context_id = context_id
        self.currency = currency

        self.inventory = Inventory(self.steam_id, self.app_id, self.context_id)
        self.trade_item_manager = TradeItemManager(self.app_id)
        self.marketplace = marketplace
        self.analyzer = PriceAnalysis()
        self.marketplace_item_parser = MarketplaceItemParser(self.app_id, self.context_id)

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

    def _sell_item(self, session: requests.Session, item: InventoryItem, price: float, max_attempts: int = 4) -> None:
        for asset_id in tqdm(item.list_asset_id, desc=f"Sell {item.name}", unit="item", ncols=80):
            for attempt in range(max_attempts):
                response = self.marketplace.create_sell_order(
                    session,
                    self.steam_id,
                    asset_id,
                    1,
                    price
                )

                if response.status_code != 200:
                    break

                if response.json().get("success"):
                    self.logger.info(
                        f"Продажа '{item.name}' ({price}): "
                        f"{response.status_code} {response.reason}"
                    )
                    break

                self.logger.debug(
                    f"Продажа '{item.name}' ({price}): "
                    f"{response.text}"
                )

    def sell_inventory(self, session: requests.Session) -> None:
        inventory_items = self.inventory.get_inventory_items(session)

        self.marketplace_item_parser.parse_actual_sell_order_items(session)

        for item in tqdm(inventory_items.values(), unit="item", ncols=80):
            item_value = self.trade_item_manager.items.get(item.name)
            if not item_value and item_value != 0:
                continue

            if not item.marketable:
                continue

            response_market_data = self.marketplace.get_item_market_data(session, item.name)
            if not response_market_data or response_market_data.status_code != 200:
                continue
            market_data = response_market_data.json()

            sales_per_day = self.marketplace.get_sales_per_day(session, item.name)
            if not sales_per_day:
                continue

            recommended_price = self.analyzer.recommend_sell_price(
                market_data, self.marketplace_item_parser.sell_orders.get(item.name), sales_per_day // 2)
            self._sell_item(session, item, recommended_price)
