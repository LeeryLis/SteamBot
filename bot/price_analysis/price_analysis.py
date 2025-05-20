from collections import Counter
from typing import Any

from bot.marketplace import SellOrderItem, BuyOrderItem

from enums import Config

from tools.file_managers import PriceAnalysisSettingsManager


class PriceAnalysis:
    def __init__(self) -> None:
        """
        :param self.acceptable_price_diff: допустимая доля разницы с медианной ценой
        :param self.reduction: значение снижения цены относительно найденной цены
        :param self.min_desired_profit: минимальный процент прибыли, ниже которого выставленный 'buy order' нужно убирать
        :param self.desired_profit: желаемый процент прибыли, ниже которого 'buy order' не выставляется
        """
        self.acceptable_price_diff = 0
        self.reduction = 0

        self.min_desired_profit = 0
        self.desired_profit = 0

        self.low_liquidity_threshold = 0
        self.min_desired_profit_low_liquidity = 0
        self.desired_profit_low_liquidity = 0

        self.change_settings()

    def change_settings(self) -> None:
        settings_manager = PriceAnalysisSettingsManager()
        settings = settings_manager.settings

        self.acceptable_price_diff = settings.get("acceptable_price_diff", settings_manager.def_acceptable_price_diff)
        self.reduction = settings.get("reduction", settings_manager.def_reduction)

        self.min_desired_profit = settings.get("min_desired_profit", settings_manager.def_min_desired_profit)
        self.desired_profit = settings.get("desired_profit", settings_manager.def_desired_profit)

        self.low_liquidity_threshold = settings.get(
            "low_liquidity_threshold", settings_manager.def_low_liquidity_threshold)
        self.min_desired_profit_low_liquidity = settings.get(
            "min_desired_profit_low_liquidity", settings_manager.def_min_desired_profit_low_liquidity)
        self.desired_profit_low_liquidity = settings.get(
            "desired_profit_low_liquidity", settings_manager.def_desired_profit_low_liquidity)

    def _find_median_price(self, market_data: dict[str, Any], my_sell_orders: list[SellOrderItem] = None,
                           max_number_prices_used: int = 10) -> float:
        my_prices_count = None
        if my_sell_orders:
            my_prices_count = Counter(order.buyer_price for order in my_sell_orders)

        price = 0
        ignore_count = 0
        for sell_order in market_data['sell_order_graph']:
            price = sell_order[0]
            count = sell_order[1]

            if my_prices_count:
                for my_price, my_count in my_prices_count.items():
                    if my_price == price:
                        ignore_count += my_count
                        del my_prices_count[my_price]
                        break

            if (count - ignore_count) >= max_number_prices_used // 2:
                return price

        return price

    def _find_first_available_price(self, market_data: dict[str, Any], median_price: float, my_sell_orders: list[SellOrderItem]) -> float:
        for sell_order in market_data.get('sell_order_graph'):
            price = sell_order[0]
            if my_sell_orders and any(sell_order.buyer_price == price for sell_order in my_sell_orders):
                continue
            if 1 - price / median_price <= self.acceptable_price_diff:
                return price
        return 0

    def get_actual_sell_order_price(self, market_data: dict[str, Any], my_sell_orders: list[SellOrderItem] = None,
                                    max_number_prices_used: int = 10) -> float:
        median_price = self._find_median_price(market_data, my_sell_orders, max_number_prices_used)
        return self._find_first_available_price(market_data, median_price, my_sell_orders)

    def recommend_sell_price(self, market_data: dict[str, Any], my_sell_orders: list[SellOrderItem] = None,
                             max_number_prices_used: int = 10) -> float:
        recommended_price = self.get_actual_sell_order_price(market_data, my_sell_orders, max_number_prices_used)
        return round(recommended_price - self.reduction, 2)

    def is_buy_order_relevant(self, market_data: dict[str, Any], sales_per_day: int,
                              my_buy_order: BuyOrderItem, max_number_prices_used: int = 10) -> bool:
        actual_sell_order_price = self.get_actual_sell_order_price(
            market_data, max_number_prices_used=max_number_prices_used)
        profit = (actual_sell_order_price * Config.WITH_COMMISSION) / my_buy_order.price - 1

        if sales_per_day < self.low_liquidity_threshold:
            return profit >= self.min_desired_profit_low_liquidity
        return profit >= self.min_desired_profit

    def _find_first_buy_order(self, market_data: dict[str, Any]) -> float:
        sell_order_graph = market_data.get('buy_order_graph')
        return sell_order_graph[0][0]

    def _find_available_price_in_buy_orders(self, market_data: dict[str, Any], sales_per_day: int) -> float:
        prev_price = 0
        for buy_order in market_data.get('buy_order_graph'):
            price = buy_order[0]
            count = buy_order[1]

            if count > sales_per_day // 2:
                return prev_price if prev_price != 0 else price

            prev_price = price

        return 0

    def recommend_buy_price(self, market_data: dict[str, Any], sales_per_day: int,
                            max_number_prices_used: int = 10) -> float | None:
        actual_sell_order_price = self.get_actual_sell_order_price(
            market_data, max_number_prices_used=max_number_prices_used)

        desired_profit = self.desired_profit_low_liquidity if sales_per_day < self.low_liquidity_threshold \
            else self.desired_profit

        max_recommended_price = self._find_first_buy_order(market_data) + self.reduction
        if ((actual_sell_order_price * Config.WITH_COMMISSION) / max_recommended_price - 1) >= desired_profit:
            return max_recommended_price

        min_recommended_price = self._find_available_price_in_buy_orders(market_data, sales_per_day)
        if ((actual_sell_order_price * Config.WITH_COMMISSION) / min_recommended_price - 1) >= desired_profit:
            return min_recommended_price

        return None
