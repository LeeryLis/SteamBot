import os
import requests
import time
from datetime import datetime, timedelta
from typing import Iterable

from dotenv import load_dotenv
from rich.text import Text
from rich.console import Console

from bot import TradeBot
from bot.marketplace import SellOrderItem
from bot.account import Account

from steam_lib.login_selenium import LoginExecutorSelenium
from steam_lib.guard import ConfirmationExecutor, ConfirmationType
from tools.file_managers import GameIDManager
from tools.console import BasicConsole, command
from utils import handle_429_status_code
from enums import Currency

from utils.exceptions import TooManyRequestsError


class TradeUserInterface(BasicConsole):
    def __init__(self):
        self.trade_bots: dict[str, TradeBot] = {}
        self.session: requests.Session = requests.Session()
        self.console = Console()
        load_dotenv()
        self.login_executor = LoginExecutorSelenium(
            os.getenv('USER_NAME'),
            os.getenv('PASSWORD'),
            os.getenv('SHARED_SECRET'),
            self.session
        )

    # region Автоматизация
    @command(
        aliases=["auto", "autojob"],
        description="Автоматически (в бесконечном цикле) произвести весь процесс: "
                    "проверка 'sell order', продажа инвентаря, подтверждения продажи, "
                    "проверка 'buy order' (если указан флаг -ub с параметром частоты проверки)",
        usage="auto <duration sec> [-ub FREQUENCY (once in this number of runs)] "
              "<game_1> [game_2] ... [game_N]",
        flags={
            "frequency_update_buy_orders": (["-ub"], "Обновлять 'buy order' с некоторой частотой")
        }
    )
    def auto_job(
            self, iteration_duration_sec: int, game_names: list[str], frequency_update_buy_orders: int = 0) -> None:
        if not self.validate_game_names(game_names):
            self.console.print(Text("Присутствуют некорректные названия игр", style="red"))
            self.console.print(Text(f"Доступные: {list(self.get_available_games().keys())}"))
            return

        update_buy_orders: bool = False
        i = 0
        while True:
            start_time = datetime.now()
            start_time_formatted = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time = start_time + timedelta(seconds=iteration_duration_sec)
            end_time_formatted = end_time.strftime("%Y-%m-%d %H:%M:%S")
            self.console.print(f"{start_time_formatted} Запуск номер {i + 1}")

            if frequency_update_buy_orders:
                update_buy_orders = i % frequency_update_buy_orders == 0

            if not self._basic_job(game_names, update_buy_orders):
                return
            i += 1

            current_time = datetime.now()
            current_time_formatted = current_time.strftime("%Y-%m-%d %H:%M:%S")
            if current_time < end_time:
                self.console.print(f"{current_time_formatted} Ожидание {end_time_formatted}")
                time.sleep((end_time - current_time).total_seconds())
            else:
                self.console.print(
                    f"{current_time_formatted} Выполнение заняло больше, чем {iteration_duration_sec} секунд. "
                    f"Следующая итерация начинается сразу.")
            self.console.print(Text("---"))

    @command(
        aliases=["job"],
        description="Произвести весь процесс:"
                    "проверка 'sell order', продажа инвентаря, подтверждения продажи, "
                    "проверка 'buy order' (если указан флаг -ub)",
        usage="job [-ub] <game_1> [game_2] ... [game_N]",
        flags={
            "update_buy_orders": (["-ub"], "Обновить 'buy order'")
        }
    )
    def _basic_job(self, game_names: list[str], update_buy_orders: bool = False) -> bool:
        if not self.validate_game_names(game_names):
            self.console.print(Text("Присутствуют некорректные названия игр", style="red"))
            self.console.print(Text(f"Доступные: {list(self.get_available_games().keys())}"))
            return False

        for game_name in game_names:
            self.console.print(Text(f"---[ {game_name} ]---", style="bold green"))

            self.console.print(Text("Update sell orders", style="yellow"))
            if not self.update_sell_orders(game_name):
                return False
            self.console.print(Text("---"))

            self.console.print(Text("Sell inventory", style="yellow"))
            if not self.sell_inventory(game_name):
                return False
            self.console.print(Text("---"))

            if update_buy_orders:
                self.console.print(Text("Update buy orders", style="yellow"))
                if not self.update_buy_orders(game_name):
                    return False
                self.console.print(Text("---"))

        return True
    # endregion

    # region Available games
    @staticmethod
    def get_available_games() -> dict[str, list[int]]:
        return GameIDManager().items

    @command(
        aliases=["games"],
        description="Вывести названия всех доступных для взаимодействия игр"
    )
    def get_available_games_names(self, print_result: bool = True) -> list[str]:
        result = list(self.get_available_games())
        if print_result:
            self.console.print(result)
        return result

    def validate_game_names(self, game_names: Iterable[str]) -> bool:
        available_games = set(self.get_available_games_names(False))
        return set(game_names).issubset(available_games)
    # endregion

    # region Login
    @command(
        aliases=["l", "login"],
        description="Зайти в аккаунт Steam (если отсутствует SHARED_SECRET В .env, "
                    "то вводить данные нужно будет вручную)"
    )
    def _login(self) -> None:
        try:
            self.login_executor.login_or_refresh_cookies()
        except Exception as e:
            self.console.print(Text(f"Error: {e}. Steam login failed"))
            return
    # endregion

    # region Bot
    @command(
        aliases=["bots"],
        description="Вывести названия всех уже созданных ботов"
    )
    def get_available_bot_names(self) -> None:
        result = list(self.trade_bots)
        self.console.print(result if len(result) > 0 else Text("Not a single bot has been created yet", style="yellow"))

    def _get_bot(self, game_name: str) -> TradeBot | None:
        trade_bot = self.trade_bots.get(game_name)
        if not trade_bot:
            trade_bot = self._create_bot(game_name)
            if not trade_bot:
                self.console.print(
                    Text(f"Игра '{game_name}' не поддерживается. Доступные: {list(self.get_available_games().keys())}")
                )
                return None

        return trade_bot

    def _create_bot(self, game_name: str) -> TradeBot | None:
        available_games = self.get_available_games()
        if game := available_games.get(game_name):
            trade_bot = TradeBot(game[0], game[1], Currency.RUB)
            self.trade_bots[game_name] = trade_bot
            return trade_bot

        return None
    # endregion

    # region Info
    @command(
        aliases=["info"],
        description="Получить информацию о выставленных на продажу вещах",
        usage="info <game_1> [game_2] ... [game_N]",
    )
    def get_multiple_sell_orders_info(self, game_names: list[str]) -> bool:
        if not self.validate_game_names(game_names):
            self.console.print(Text("Присутствуют некорректные названия игр", style="red"))
            self.console.print(Text(f"Доступные: {list(self.get_available_games().keys())}"))
            return False

        for game_name in game_names:
            self._get_sell_orders_info(game_name)
            self.console.print("---")
        return True

    def _get_sell_orders_info(self, game_name: str) -> None:
        self._login()

        if trade_bot := self._get_bot(game_name):
            sell_orders = dict()
            try:
                sell_orders: dict[str, list[SellOrderItem]] = trade_bot.get_sell_orders_info(self.session)
            except TooManyRequestsError as ex:
                Console().print(
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                    f"Ошибка: {ex}"
                )

            self.console.print(Text(f"---[ {game_name} ]---", style="bold green"))

            total_count = 0
            total_price = 0
            total_buyer_price = 0
            for sell_order_list in sell_orders.values():
                for sell_order in sell_order_list:
                    total_count += sell_order.count
                    total_price += sell_order.seller_price
                    total_buyer_price += sell_order.buyer_price

            self.console.print(Text(f"Total price: {total_price:.2f}", style="yellow2"))
            self.console.print(Text(f"Total buyer price: {total_buyer_price:.2f}", style="yellow"))
            self.console.print(Text(f"Total count: {total_count}", style="cyan"))

    @command(
        aliases=["inv"],
        description="Получить количество доступных для продажи вещей в инвентаре",
        usage="inv <game_1> [game_2] ... [game_N]",
    )
    def get_multiple_marketable_inventory(self, game_names: list[str]) -> bool:
        if not self.validate_game_names(game_names):
            self.console.print(Text("Присутствуют некорректные названия игр", style="red"))
            self.console.print(Text(f"Доступные: {list(self.get_available_games().keys())}"))
            return False

        for game_name in game_names:
            self._get_marketable_inventory(game_name)
            self.console.print("---")
        return True

    def _get_marketable_inventory(self, game_name: str) -> None:
        self._login()

        if trade_bot := self._get_bot(game_name):
            self.console.print(Text(f"---[ {game_name} ]---", style="bold green"))
            try:
                currently, not_yet, total = trade_bot.get_marketable_inventory(self.session)
                self.console.print(Text(f"Currently marketable: {currently}", style="yellow2"))
                self.console.print(Text(f"Currently not marketable: {not_yet}", style="yellow"))
                self.console.print(Text(f"Total: {total}", style="cyan"))
            except TooManyRequestsError as ex:
                Console().print(
                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
                    f"Ошибка: {ex}"
                )

    @command(
        aliases=["bl", "balance", "money"],
        description="Вывести баланс кошелька Steam",
        usage="balance",
    )
    def get_account_balance(self) -> None:
        self._login()

        account = Account()
        balance, pending, total = account.get_account_balance(self.session)

        self.console.print(Text(f"Wallet Balance: {balance:.2f}", style="cyan"))
        self.console.print(Text(f"Pending Balance: {pending:.2f}", style="yellow"))
        self.console.print(Text(f"Total: {total:.2f}", style="green"))

    @command(
        aliases=["history", "summarize"],
        description="Собрать историю торговой площадки",
        usage="history"
    )
    def summarize_market_history(self) -> None:
        self._login()

        account = Account()
        account.summarize_market_history(self.session)
    # endregion

    # region Fundamental commands
    @command(
        aliases=["us", "update_sell_orders"],
        description="Обновить выставленные на продажу ордера (снять нерелевантные)",
        usage="us <game>"
    )
    def update_sell_orders(self, game_name: str) -> bool:
        self._login()

        if trade_bot := self._get_bot(game_name):
            return not handle_429_status_code(trade_bot.update_sell_orders, self.session)
        return False

    @command(
        aliases=["ub", "update_buy_orders"],
        description="Обновить запросы на покупку (убрать нерелевантные и создать новые подходящие)",
        usage="ub <game>"
    )
    def update_buy_orders(self, game_name: str) -> bool:
        self._login()

        if trade_bot := self._get_bot(game_name):
            result = handle_429_status_code(trade_bot.update_buy_orders, self.session)
            trade_bot.marketplace.save_cache_sales_per_day()
            return not result
        return False

    @command(
        aliases=["si", "sell_inventory"],
        description="Продать вещи из инвентаря",
        usage="si <game>",
    )
    def sell_inventory(self, game_name: str) -> bool:
        self._login()

        if trade_bot := self._get_bot(game_name):
            return not handle_429_status_code(trade_bot.sell_inventory, self.session)
        return False

    @command(
        aliases=["conf", "confirm_sell"],
        description="Подтверждение создание лотов (когда требуется мобильное подтверждение)",
    )
    def confirm_all_sell_orders(self) -> None:
        self._login()

        ConfirmationExecutor(
            os.getenv('IDENTITY_SECRET'),
            os.getenv('STEAM_ID'),
            self.session
        ).allow_all_confirmations([ConfirmationType.CREATE_LISTING])

        self.console.print(Text("done"))
    # endregion

    # region DST
    @command(
        aliases=["spiffy"],
        description="Работа со spiffy в DST",
        usage="spiffy <flag>",
        flags={
            "cancel": (["-c"], "Снять все spiffy с продажи"),
            "price": (["-s"], "Продать все spiffy по заданной цене")
        }
    )
    def dst_cancel_sell_spiffy(self, price: float = 0, cancel: bool = False) -> bool:
        self._login()

        if trade_bot := self._get_bot("dst"):
            if price != 0:
                return not handle_429_status_code(trade_bot.dst_sell_inventory, self.session, price)
            if cancel:
                return not handle_429_status_code(trade_bot.dst_cancel_sell_orders, self.session)
        self.console.print(Text("Необходимо выставить флаг команды", style="red"))
        return False

    @command(
        aliases=["dist"],
        description="Работа с distinguished в DST",
        usage="dist <flag>",
        flags={
            "cancel": (["-c"], "Снять все distinguished с продажи"),
            "price": (["-s"], "Продать все distinguished по заданной цене")
        }
    )
    def dst_cancel_sell_distinguished(self, price: float = 0, cancel: bool = False) -> bool:
        self._login()

        if trade_bot := self._get_bot("dst"):
            if price != 0:
                return not handle_429_status_code(trade_bot.dst_sell_inventory, self.session, price, False)
            if cancel:
                return not handle_429_status_code(trade_bot.dst_cancel_sell_orders, self.session, False)
        self.console.print(Text("Необходимо выставить флаг команды", style="red"))
        return False
    # endregion


if __name__ == "__main__":
    TradeUserInterface().run("TradeUI")
