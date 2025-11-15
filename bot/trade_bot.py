import os
from typing import Any

import requests
from tqdm import tqdm

from bot.inventory import Inventory, InventoryItem
from bot.marketplace import Marketplace, SellOrderItem
from bot.price_analysis import PriceAnalysis
from bot.marketplace import MarketplaceItemParser, BuyOrderItem
from tools.file_managers import TradeItemManager, TempTradeItemManager
from steam_lib.guard import ConfirmationExecutor, ConfirmationType
from tools import BasicLogger

from enums.config import Config


class TradeBot(BasicLogger):
    def __init__(self, app_id: int, context_id: int, currency: int) -> None:
        super().__init__(
            logger_name=f"{self.__class__.__name__}{app_id}",
            dir_specify=str(app_id),
            file_name=f"{self.__class__.__name__}"
        )

        self.needed_confirmation_count = 0
        self.confirmation_threshold = 100

        self.app_id = app_id
        self.context_id = context_id
        self.currency = currency

        self.inventory = Inventory(self.app_id, self.context_id)
        self.trade_item_manager = TradeItemManager(self.app_id)
        self.temp_trade_item_manager = TempTradeItemManager(self.app_id)
        self.marketplace = Marketplace(app_id, context_id, currency)
        self.price_analysis = PriceAnalysis()

        self.marketplace_item_parser = MarketplaceItemParser(self.app_id, self.context_id)

    def get_sell_orders_info(self, session: requests.Session) -> dict[str, list[SellOrderItem]]:
        return self.marketplace_item_parser.parse_actual_sell_order_items(session)

    def get_marketable_inventory(self, session: requests.Session) -> list[int]:
        inventory_items = self.inventory.get_inventory_items(session)

        result = [0, 0, 0]  # Currently marketable, currently not marketable, total
        for item in inventory_items.values():
            if item.marketable:
                result[0] += len(item.list_asset_id)
            elif item.has_owner_descriptions:
                result[1] += len(item.list_asset_id)
        result[2] = result[0] + result[1]

        return result

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

        for item_name in tqdm(trade_item_names, unit="order", ncols=Config.TQDM_CONSOLE_WIDTH):
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
                elif response.status_code == 406:
                    self.logger.info(
                        f"Buy order '{item_name}' need confirmation "
                        f"{response.status_code} {response.reason}"
                    )
                    ConfirmationExecutor(
                        os.getenv('IDENTITY_SECRET'),
                        os.getenv('STEAM_ID'),
                        session
                    ).allow_buy_order_confirmation()
                    confirmation_id = response.json().get('confirmation').get('confirmation_id')
                    response = self.marketplace.create_buy_order(
                        session,
                        item_name,
                        recommended_buy_price,
                        self.trade_item_manager.items.get(item_name),
                        confirmation_id
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
                else:
                    self.logger.error(
                        f"Buy order '{item_name}' "
                        f"({round(recommended_buy_price, 2)} x {self.trade_item_manager.items.get(item_name)}): "
                        f"{response.status_code} {response.reason}"
                    )

    def _cancel_incorrect_sell_orders(
            self, session: requests.Session, item_name: str, actual_price: float) -> None:
        items = self.marketplace_item_parser.sell_orders.get(item_name)
        with tqdm(items, unit="order", ncols=Config.TQDM_CONSOLE_WIDTH) as pbar:
            pbar.set_description(f"Check '{item_name}'")
            for item in pbar:
                if item.buyer_price > actual_price:
                    pbar.set_description(f"Cancel '{item_name}'")
                    response = self.marketplace.cancel_sell_order(session, item.order_id)
                    if response.status_code == 200:
                        self.logger.info(
                            f"Cancel sell order '{item_name}': "
                            f"{response.status_code} {response.reason}")
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

        with tqdm(self.marketplace_item_parser.sell_orders.keys(), unit="order", ncols=Config.TQDM_CONSOLE_WIDTH) as pbar:
            for item_name in pbar:
                # pbar.set_description(f"{item_name}")
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

    def _confirm_all_sell_orders(self, session: requests.Session) -> None:
        ConfirmationExecutor(
            os.getenv('IDENTITY_SECRET'),
            os.getenv('STEAM_ID'),
            session
        ).allow_all_confirmations([ConfirmationType.CREATE_LISTING])
        self.needed_confirmation_count = 0

    def _item_sold_confirmation_checker(self, session: requests.Session, count: int = 1) -> None:
        self.needed_confirmation_count += count
        if self.needed_confirmation_count >= self.confirmation_threshold:
            self._confirm_all_sell_orders(session)

    def _sell_item(
            self, session: requests.Session, item: InventoryItem, price: float, max_attempts: int = 4,
            log_success: bool = True
    ) -> None:
        for asset_id in tqdm(item.list_asset_id, desc=f"Sell '{item.name}'", unit="item", ncols=Config.TQDM_CONSOLE_WIDTH):
            for attempt in range(max_attempts):
                response = self.marketplace.create_sell_order(
                    session,
                    os.getenv('STEAM_ID'),
                    asset_id,
                    1,
                    price
                )

                if response.status_code != 200:
                    break

                if response.json().get("success"):
                    if log_success:
                        self.logger.info(
                            f"Продажа '{item.name}' ({round(price, 2)}): "
                            f"{response.status_code} {response.reason}"
                        )
                    self._item_sold_confirmation_checker(session)
                    break

                self.logger.debug(
                    f"Продажа '{item.name}' ({round(price, 2)}): "
                    f"{response.text}"
                )

    def sell_inventory(self, session: requests.Session) -> None:
        inventory_items = self.inventory.get_inventory_items(session)

        self.marketplace_item_parser.parse_actual_sell_order_items(session)

        items = [item for item in inventory_items.values() if item.marketable]
        with tqdm(items, unit="item", ncols=Config.TQDM_CONSOLE_WIDTH) as pbar:
            for item in pbar:
                # pbar.set_description(f"{item.name}")
                item_value = self.trade_item_manager.items.get(item.name)
                if not item_value and item_value != 0:
                    continue

                response_market_data = self.marketplace.get_item_market_data(session, item.name)
                if not response_market_data or response_market_data.status_code != 200:
                    continue
                market_data = response_market_data.json()

                sales_per_day = self.marketplace.get_sales_per_day(session, item.name)
                if not sales_per_day:
                    continue

                recommended_price = self.price_analysis.recommend_sell_price(
                    market_data, self.marketplace_item_parser.sell_orders.get(item.name), sales_per_day // 2)
                if recommended_price:
                    self._sell_item(session, item, recommended_price)

        self._confirm_all_sell_orders(session)

    # region DST
    @staticmethod
    def _is_dst_spiffy(item_hash_name: str) -> bool:
        return item_hash_name in [
            "BACKPACK_BASIC_BLUE_CATCOON",
            "BACKPACK_BASIC_GREEN_OLIVE",
            "BACKPACK_BUCKLE_GREY_PEWTER",
            "BACKPACK_BUCKLE_NAVY_PHTHALO",
            "BACKPACK_BUCKLE_RED_ROOK",
            "BODY_CABLEKNIT_SWEATER_TAN_KHAKI",
            "BODY_COATDRESS_RED_HIGGSBURY",
            "WINTERHAT_STOCKING_CAP_GREEN_FOREST",
            "FEET_SWIMFLIPPERS_BLACK_SCRIBBLE",
            "FLOWERHAT_HOLLY_WREATH",
            "LEGS_PJ_BLUE_AGEAN",
            "LEGS_PJ_PURPLE_MAUVE",
            "BODY_PJ_BLUE_AGEAN",
            "BODY_PJ_PURPLE_MAUVE",
            "BODY_OVERALLS_TAN_GRASS",
            "BODY_OVERALLS_BLUE_DENIM",
            "BODY_OVERALLS_BLACK_SCRIBBLE",
            "BODY_OVERALLS_NAVY_OCEAN",
            "BODY_OVERALLS_BROWN_FAWN",
            "BODY_OUTERWEAR_QUILTED_RED_CARDINAL",
            "FLOWERHAT_RIBBON_WREATH",
            "BACKPACK_CAMPING_ORANGE_CARROT",
            "BACKPACK_CAMPING_RED_KOALEFANT",
            "BACKPACK_CAMPING_GREEN_VIRIDIAN",
            "BODY_SILK_EVENINGROBE_YELLOW_GOLDENROD",
            "BODY_SILK_EVENINGROBE_PINK_EWECUS",
            "BODY_SILK_EVENINGROBE_BLUE_FROST",
            "BODY_SILK_EVENINGROBE_RED_RUMP",
            "BODY_TANKTOP_TIECOLLAR_YELLOW_GOLDENROD",
            "BODY_SWIMSUIT2_BLUE_LIGHTNING",
            "FEET_SWIMSHOES_BLUE_LIGHTNING",
            "BODY_SWIMSUIT_RED_RUBY",
            "BODY_TOGA_WHITE_PURE",
            "BODY_TRENCHCOAT_TAN_CLAY",
            "BODY_TRENCHCOAT_GREY_DARK",
            "BODY_TRENCHCOAT_YELLOW_STRAW",
            "BODY_TRENCHCOAT_BROWN_FAWN"
        ]

    @staticmethod
    def _is_dst_distinguished(item_hash_name: str) -> bool:
        return item_hash_name in [
            "ENDTABLE_VINTAGE",
            "ENDTABLE_CARPET",
            "FEET_BUNNYSLIPPERS_PURPLE_MAUVE",
            "BODY_DRESS_FLOUNCY_TAN_CREAM",
            "FEET_FUZZYSLIPPERS_BLUE_ICE",
            "BODY_WAXWELL_COOK",
            "BODY_SLEEPGOWN_BLUE_ICE",
            "BODY_SLEEPGOWN_PURPLE_LAVENDER",
            "BEDROLL_FURRY_QUILT_BLUE_FROST",
            "BEDROLL_FURRY_QUILT_WHITE_IVORY",
            "BODY_JACKET_SHEARLING_ORANGE_SALMON",
            "BODY_SILK_LOUNGEWEAR_BLACK_DAVYS",
            "BODY_SILK_LOUNGEWEAR_GREEN_LAUREL",
            "BODY_SILK_LOUNGEWEAR_RED_CRANBERRY",
            "BODY_SILK_LOUNGEWEAR_WHITE_MARBLE",
            "BODY_JACKET_TOGGLE_NAVY_PHTHALO",
            "BODY_WEBBER_COOK",
            "BODY_WENDY_COOK",
            "BODY_WES_COOK",
            "BODY_WICKERBOTTOM_COOK",
            "BODY_WATHGRITHR_COOK",
            "BODY_WILLOW_COOK",
            "BODY_WILSON_COOK",
            "BODY_WINONA_COOK",
            "BODY_WOLFGANG_COOK",
            "BODY_WOODIE_COOK",
            "BODY_WX78_COOK",
            "BODY_DRESS_YACHTSUIT_WHITE_PURE",
            "BODY_YULED_DRESS",
            "BODY_YULED_COAT"
        ]

    def dst_cancel_sell_orders(self, session: requests.Session, is_spiffy: bool = True) -> None:
        self.marketplace_item_parser.parse_actual_sell_order_items(session)

        sell_order_items = self.marketplace_item_parser.sell_orders.keys()
        if is_spiffy:
            sell_order_items = [item for item in sell_order_items if self._is_dst_spiffy(item)]
        else:
            sell_order_items = [item for item in sell_order_items if self._is_dst_distinguished(item)]

        with tqdm(sell_order_items, unit="order", ncols=Config.TQDM_CONSOLE_WIDTH) as pbar:
            for item_name in pbar:
                items = self.marketplace_item_parser.sell_orders.get(item_name)
                with tqdm(items, unit="order", ncols=Config.TQDM_CONSOLE_WIDTH) as inner_pbar:
                    inner_pbar.set_description(f"Cancel '{item_name}'")
                    for item in inner_pbar:
                        response = self.marketplace.cancel_sell_order(session, item.order_id)
                        if response.status_code != 200:
                            self.logger.error(
                                f"Cancel sell order '{item_name}': "
                                f"{response.status_code} {response.reason}"
                            )

    def dst_sell_inventory(self, session: requests.Session, price: float, is_spiffy: bool = True) -> None:
        inventory_items = self.inventory.get_inventory_items(session)
        actual_price = price / Config.WITH_COMMISSION

        items = [item for item in inventory_items.values() if item.marketable]
        if is_spiffy:
            items = [item for item in items if self._is_dst_spiffy(item.name)]
        else:
            items = [item for item in items if self._is_dst_distinguished(item.name)]

        with tqdm(items, unit="item", ncols=Config.TQDM_CONSOLE_WIDTH) as pbar:
            for item in pbar:
                self._sell_item(session, item, actual_price, log_success=False)

        self._confirm_all_sell_orders(session)
    # endregion
