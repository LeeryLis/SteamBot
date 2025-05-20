import json
import os
from rich.console import Console
from rich.text import Text

from _root import project_root


class PriceAnalysisSettingsManager:
    def __init__(self, file_name: str = "price_analysis_settings.json") -> None:
        self.file_path = project_root / f'data/{file_name}'
        self.settings = {}
        self.load_settings()

        self.def_acceptable_price_diff: float = 0.03
        self.def_reduction: float = 0.03
        self.def_min_desired_profit: float = 0.02
        self.def_desired_profit: float = 0.04

        self.def_low_liquidity_threshold = 10
        self.def_min_desired_profit_low_liquidity: float = 0.04
        self.def_desired_profit_low_liquidity: float = 0.07

        self.console = Console()

    def load_settings(self) -> None:
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r', encoding='utf-8') as file:
                self.settings = json.load(file)
        else:
            self.settings = {}

    def save_settings(self) -> None:
        with open(self.file_path, 'w', encoding='utf-8') as file:
            json.dump(self.settings, file, ensure_ascii=False, indent=4)

    def manual_change_settings(self) -> None:
        self.console.print("Анализ цен продажи")
        try:
            acceptable_price_diff = float(
                self.console.input(f"Введите допустимую долю разницы с медианной ценой (def = "
                                   f"{self.def_acceptable_price_diff}): "))
            reduction = float(
                self.console.input(f"Введите значение снижения цены относительно найденной цены (def = "
                                   f"{self.def_reduction}): "))

            self.console.print("Анализ цен покупки")
            min_desired_profit = float(
                self.console.input(
                    f"Введите минимальную долю прибыли, ниже которой ВЫСТАВЛЕННЫЙ 'buy order' нужно убирать (def = "
                    f"{self.def_min_desired_profit}): "))
            desired_profit = float(
                self.console.input(
                    f"Введите желаемую долю прибыли, ниже которой НОВЫЙ 'buy order' не выставляется (def = "
                    f"{self.def_desired_profit}): "))

            self.console.print("Низколиквидные предметы")
            low_liquidity_threshold = int(
                self.console.input(
                    f"Введите порог низкой ликвидности (def = "
                    f"{self.def_low_liquidity_threshold}): "))
            min_desired_profit_low_liquidity = float(
                self.console.input(
                    f"Для низколиквидных. "
                    f"Введите минимальную долю прибыли, ниже которой ВЫСТАВЛЕННЫЙ 'buy order' нужно убирать (def = "
                    f"{self.def_min_desired_profit_low_liquidity}): "))
            desired_profit_low_liquidity = float(
                self.console.input(
                    f"Для низколиквидных. "
                    f"Введите желаемую долю прибыли, ниже которой НОВЫЙ 'buy order' не выставляется (def = "
                    f"{self.def_desired_profit_low_liquidity}): "))
        except ValueError:
            self.console.print(Text("Недопустимый ввод", style="red"))
            return

        self.settings["acceptable_price_diff"] = acceptable_price_diff
        self.settings["reduction"] = reduction
        self.settings["min_desired_profit"] = min_desired_profit
        self.settings["desired_profit"] = desired_profit
        self.settings["low_liquidity_threshold"] = low_liquidity_threshold
        self.settings["min_desired_profit_low_liquidity"] = min_desired_profit_low_liquidity
        self.settings["desired_profit_low_liquidity"] = desired_profit_low_liquidity
        self.save_settings()
        self.console.print("Значения сохранены")

    def set_default_settings(self) -> None:
        self.settings["acceptable_price_diff"] = self.def_acceptable_price_diff
        self.settings["reduction"] = self.def_reduction
        self.settings["min_desired_profit"] = self.def_min_desired_profit
        self.settings["desired_profit"] = self.def_desired_profit
        self.settings["low_liquidity_threshold"] = self.def_low_liquidity_threshold
        self.settings["min_desired_profit_low_liquidity"] = self.def_min_desired_profit_low_liquidity
        self.settings["desired_profit_low_liquidity"] = self.def_desired_profit_low_liquidity
        self.save_settings()
        self.console.print("Установлены значения по умолчанию")

    def print_settings(self):
        self.console.print(self.settings)
