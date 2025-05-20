import logging
from logging.handlers import RotatingFileHandler
import os
from typing import Any

import requests
from tqdm import tqdm

from bot.inventory import InventorySeller
from bot.marketplace import Marketplace
from bot.price_analysis import PriceAnalysis
from bot.marketplace import MarketplaceItemParser, BuyOrderItem
from tools.file_managers import TradeItemManager, TempTradeItemManager

from _root import project_root


class TradeBot:
    def __init__(self, steam_id: str, app_id: int, context_id: int, currency: int) -> None:
        self.steam_id = steam_id
        self.app_id = app_id
        self.context_id = context_id
        self.currency = currency

        self.trade_item_manager = TradeItemManager(self.app_id)
        self.temp_trade_item_manager = TempTradeItemManager(self.app_id)
        self.marketplace = Marketplace(app_id, context_id, currency)
        self.inventory_seller = InventorySeller(
            self.steam_id, self.app_id, self.context_id, self.currency, self.marketplace)
        self.price_analysis = PriceAnalysis()

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

    def _cancel_incorrect_buy_orders(
            self, session: requests.Session, buy_order: BuyOrderItem, market_data: dict[str, Any],
            sales_per_day: int) -> bool:
        max_number_prices_used = sales_per_day // 2
        if self.price_analysis.is_buy_order_relevant(market_data, sales_per_day, buy_order, max_number_prices_used):
            return False

        response = self.marketplace.cancel_buy_order(session, buy_order.order_id)
        if response.status_code == 200:
            self.logger.info(
                f"Cancel buy order '{buy_order.name}': "
                f"{response.status_code} {response.reason}"
            )
            return True
        else:
            self.logger.info(
                f"Cancel buy order '{buy_order.name}': "
                f"{response.status_code} {response.reason}"
            )
            return False

    def update_buy_orders(self, session: requests.Session) -> None:
        """
        Снимет некорректные 'buy order',
        а также выставит новые 'buy order' по рекомендуемой цене (если таковая будет найдена)
        """
        self.trade_item_manager.load_items()
        self.marketplace.item_manager.load_items()
        trade_item_names = self.trade_item_manager.items.keys()

        actual_buy_orders = self.marketplace_item_parser.parse_actual_buy_order_items(session)

        for item_name in tqdm(trade_item_names, unit="order", ncols=80):
            if self.trade_item_manager.items.get(item_name) == 0 and not actual_buy_orders.get(item_name):
                continue

            response_market_data = self.marketplace.get_item_market_data(session, item_name)
            if not response_market_data or response_market_data.status_code != 200:
                continue
            market_data = response_market_data.json()

            sales_per_day = self.marketplace.get_sales_per_day(session, item_name)
            if not sales_per_day:
                continue

            if buy_order := actual_buy_orders.get(item_name):
                if not self._cancel_incorrect_buy_orders(session, buy_order, market_data, sales_per_day):
                    continue

            recommended_buy_price = self.price_analysis.recommend_buy_price(
                market_data, sales_per_day, sales_per_day // 2)
            if recommended_buy_price:
                response = self.marketplace.create_buy_order(
                    session,
                    item_name,
                    recommended_buy_price,
                    self.trade_item_manager.items.get(item_name)
                )
                if response.status_code == 200:
                    self.logger.info(
                        f"Buy order '{item_name}' "
                        f"({round(recommended_buy_price, 2)} x {self.trade_item_manager.items.get(item_name)}): "
                        f"{response.status_code} {response.reason}"
                    )
                else:
                    self.logger.error(
                        f"Buy order '{item_name}' "
                        f"({round(recommended_buy_price, 2)} x {self.trade_item_manager.items.get(item_name)}): "
                        f"{response.status_code} {response.reason}"
                    )

    def _cancel_incorrect_sell_orders(
            self, session: requests.Session, item_name: str, actual_price: float) -> None:
        items = self.marketplace_item_parser.sell_orders.get(item_name)
        for item in items:
            if item.buyer_price > actual_price:
                for attempt in range(4):
                    response = self.marketplace.cancel_sell_order(session, item.order_id)
                    if response.status_code == 200:
                        self.logger.info(
                            f"Cancel sell order '{item_name}': "
                            f"{response.status_code} {response.reason}")
                        break
                    else:
                        self.logger.error(
                            f"Cancel sell order '{item_name}': "
                            f"{response.status_code} {response.reason}"
                        )

    def update_sell_orders(self, session: requests.Session) -> None:
        """
        Выставленные некорректные 'sell order' будут сняты,
        но метод не будет выставлять их по корректной цене (нужно вызвать метод 'sell_inventory')
        """
        self.marketplace_item_parser.parse_actual_sell_order_items(session)

        for item_name in tqdm(self.marketplace_item_parser.sell_orders.keys(), unit="order", ncols=80):
            if item_name not in self.trade_item_manager.items:
                continue

            if item_name in self.temp_trade_item_manager.items:
                continue

            response_market_data = self.marketplace.get_item_market_data(session, item_name)
            if not response_market_data or response_market_data.status_code != 200:
                continue
            market_data = response_market_data.json()

            sales_per_day = self.marketplace.get_sales_per_day(session, item_name)
            if not sales_per_day:
                continue

            actual_sell_order_price = self.price_analysis.get_actual_sell_order_price(
                market_data,
                self.marketplace_item_parser.sell_orders.get(item_name),
                sales_per_day // 2
            )

            self._cancel_incorrect_sell_orders(session, item_name, actual_sell_order_price)

    def sell_inventory(self, session: requests.Session) -> None:
        self.inventory_seller.sell_inventory(session)
