import os
import requests
import pickle
import time
from datetime import datetime, timedelta
from typing import Iterable

from dotenv import load_dotenv
from rich.text import Text
from rich.console import Console

from bot import TradeBot
from bot.marketplace import MarketplaceItemParser

from enums import Currency

from steam_lib.login import LoginExecutor
from steam_lib.guard import ConfirmationExecutor, ConfirmationType
from tools.file_managers import GameIDManager
from tools.console import BasicConsole, ConsoleManager, Param, ParamType
from utils import handle_429_status_code

from _root import project_root

class TradeUserInterface(BasicConsole):
    def __init__(self):
        self.trade_bots: dict[str, TradeBot] = {}
        self.steam_id: str = ''
        self.session: requests.Session = requests.Session()

        self.console = Console()

        self.cookies_filename = f"{project_root}/data/saved_session/cookies.pkl"
        self.steam_id_filename = f"{project_root}/data/saved_session/steam_id.txt"

        load_dotenv()

    def _register_commands(self, console_manager: ConsoleManager) -> None:
        # region Print games
        console_manager.register_command(
            aliases=["games"],
            description="Вывести названия всех доступных для взаимодействия игр",
            action=self.get_available_games_names
        )
        # endregion
        # region Print bots
        console_manager.register_command(
            aliases=["bots"],
            description="Вывести названия всех уже созданных ботов",
            action=self.get_available_bot_names
        )
        # endregion
        # region Job (us - si - conf - ub)
        console_manager.register_command(
            action=self.job,
            aliases=["job"],
            description="Произвести весь процесс:"
                        "проверка 'sell order', продажа инвентаря, подтверждения продажи, проверка 'buy order'",
            usage="job <game_1> [game_2] ... [game_N]",
            print_result=False,
            params={
                "-ub": Param(
                    action=self.job_without_ub,
                    description="проверка 'sell order', продажа инвентаря, подтверждения продажи "\
                                "(без 'update_buy_orders')",
                    param_type=ParamType.LOGIC,
                    usage="job -ub <game_1> [game_2] ... [game_N]"
                )
            }
        )
        # endregion
        # region Auto job (while True: us - si - conf - ub)
        console_manager.register_command(
            action=self.auto_job,
            aliases=["auto", "autojob"],
            description="Автоматически (в бесконечном цикле) произвести весь процесс: "
                        "проверка 'sell order', продажа инвентаря, подтверждения продажи, проверка 'buy order'",
            usage="auto <duration sec> <update buy order frequency (once in this number of runs)> "
                  "<game_1> [game_2] ... [game_N]",
            print_result=False,
            params={
                "-ub": Param(
                    action=self.auto_job_without_ub,
                    description="Автоматическая (в бесконечном цикле) проверка 'sell order', "
                                "продажа инвентаря, подтверждения продажи (без 'update_buy_orders')",
                    param_type=ParamType.LOGIC,
                    usage="auto -ub <duration sec> <game_1> [game_2] ... [game_N]",
                    arg_number=1
                )
            }
        )
        # endregion
        # region Login
        console_manager.register_command(
            aliases=["l", "login"],
            description="Use saved cookies. The connection will be tested. "
                        "If the cookies are outdated, a new account login will be performed "
                        "(new cookies will be saved)",
            action=self.restore_connection,
            print_result=False
        )
        # endregion
        # region Update sell orders
        console_manager.register_command(
            aliases=["us", "update_sell_orders"],
            description="Update sell orders (remove incorrect orders)",
            action=self.update_sell_orders,
            usage="us <game>",
            print_result=False
        )
        # endregion
        # region Update buy orders
        console_manager.register_command(
            aliases=["ub", "update_buy_orders"],
            description="Update buy orders (remove incorrect AND create new orders if there is a suitable price)",
            action=self.update_buy_orders,
            usage="ub <game>",
            print_result=False
        )
        # endregion
        # region Sell inventory
        console_manager.register_command(
            aliases=["si", "sell_inventory"],
            description="Create sell orders from inventory items",
            action=self.sell_inventory,
            usage="si <game>",
            print_result=False
        )
        # endregion
        # region Confirmation
        console_manager.register_command(
            aliases=["conf", "confirm_sell"],
            description="Confirm all sell orders (after sell inventory)",
            action=self.confirm_all_sell_orders,
            print_result=False
        )
        # endregion

    # region Connection
    def is_connection_alive(self) -> bool:
        def_app_id, def_context_id = 440, 2
        response = MarketplaceItemParser(def_app_id, def_context_id).get_sell_orders_page(self.session, True)
        return response.status_code == 200

    def restore_connection(self) -> None:
        self.session = requests.Session()
        # self.console.print(self.load_cookies())
        self.load_cookies()
        if not self.is_connection_alive():
            self.session = requests.Session()
            # self.console.print(Text(f"Куки устарели, новый вход в аккаунт", style="cyan"))
            # self.console.print(*self.login_and_save_cookies(), sep="")
            self.login_and_save_cookies()
    # endregion

    # region Автоматизация
    def auto_job_without_ub(self, iteration_duration_sec: int, *game_names: str) -> None:
        if not self.validate_game_names(game_names):
            self.console.print(Text("Присутствуют некорректные названия игр", style="red"))
            self.console.print(Text(f"Доступные: {list(self.get_available_games().keys())}"))
            return

        i = 0
        while True:
            start_time = datetime.now()
            start_time_formatted = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time = start_time + timedelta(seconds=iteration_duration_sec)
            end_time_formatted = end_time.strftime("%Y-%m-%d %H:%M:%S")
            self.console.print(f"{start_time_formatted} Запуск номер {i + 1}")

            if not self._basic_job(False, *game_names):
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

    def auto_job(self, iteration_duration_sec: int, frequency_update_buy_orders: int, *game_names: str) -> None:
        if not self.validate_game_names(game_names):
            self.console.print(Text("Присутствуют некорректные названия игр", style="red"))
            self.console.print(Text(f"Доступные: {list(self.get_available_games().keys())}"))
            return

        i = 0
        while True:
            start_time = datetime.now()
            start_time_formatted = start_time.strftime("%Y-%m-%d %H:%M:%S")
            end_time = start_time + timedelta(seconds=iteration_duration_sec)
            end_time_formatted = end_time.strftime("%Y-%m-%d %H:%M:%S")
            self.console.print(f"{start_time_formatted} Запуск номер {i + 1}")

            if not self._basic_job(i % frequency_update_buy_orders == 0, *game_names):
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

    def job_without_ub(self, *game_names: str) -> None:
        self._basic_job(False, *game_names)

    def job(self, *game_names: str) -> None:
        self._basic_job(True, *game_names)

    def _basic_job(self, update_buy_orders: bool, *game_names: str) -> bool:
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

            self.console.print(Text("Confirm all sell orders", style="yellow"))
            self.confirm_all_sell_orders()
            self.console.print(Text("---"))

            if update_buy_orders:
                self.console.print(Text("Update buy orders", style="yellow"))
                if not self.update_buy_orders(game_name):
                    return False
                self.console.print(Text("---"))

        return True

    # endregion

    # region Available games
    def get_available_games(self) -> dict[str, list[int]]:
        return GameIDManager().items

    def get_available_games_names(self) -> list[str]:
        return list(self.get_available_games())

    def validate_game_names(self, game_names: Iterable[str]) -> bool:
        available_games = set(self.get_available_games_names())
        return set(game_names).issubset(available_games)
    # endregion

    # region Login and cookies
    def load_cookies(self) -> Text:
        try:
            with open(self.cookies_filename, 'rb') as f:
                self.session.cookies.update(pickle.load(f))
            with open(self.steam_id_filename, 'r') as f:
                self.steam_id = int(f.read())
        except FileNotFoundError:
            return Text("No previous cookies found", style="red")

        return Text("Cookies loaded successfully")

    def _save_cookies(self) -> Text:
        with open(self.cookies_filename, 'wb') as f:
            pickle.dump(self.session.cookies, f)
        with open(self.steam_id_filename, 'w') as f:
            f.write(self.steam_id)
        return Text("Cookies saved successfully")

    def login_and_save_cookies(self) -> list[Text]:
        self.steam_id = ''
        result = [self._login()]
        if self.steam_id != '':
            result.append("\n")
            result.append(self._save_cookies())
        return result

    def _login(self) -> Text:
        if self.steam_id != '':
            return Text("Вы уже вошли в аккаунт")

        load_dotenv()
        login_executor = LoginExecutor(
            os.getenv('USER_NAME'),
            os.getenv('PASSWORD'),
            os.getenv('SHARED_SECRET'),
            self.session
        )
        try:
            self.steam_id = login_executor.login()
        except Exception as e:
            return Text(f"Error: {e}. Steam login failed")
        return Text("Вы успешно вошли в аккаунт")
    # endregion

    # region Bot
    def get_available_bot_names(self) -> list[str] | Text:
        result = list(self.trade_bots)
        return result if len(result) > 0 else Text("Not a single bot has been created yet", style="yellow")

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
            trade_bot = TradeBot(self.steam_id, game[0], game[1], Currency.RUB)
            self.trade_bots[game_name] = trade_bot
            return trade_bot

        return None
    # endregion

    def update_sell_orders(self, game_name: str) -> bool:
        self.restore_connection()

        if trade_bot := self._get_bot(game_name):
            return not handle_429_status_code(trade_bot.update_sell_orders, self.session)
        return False

    def update_buy_orders(self, game_name: str) -> bool:
        self.restore_connection()

        if trade_bot := self._get_bot(game_name):
            result = handle_429_status_code(trade_bot.update_buy_orders, self.session)
            trade_bot.marketplace.save_cache_sales_per_day()
            return not result
        return False

    def sell_inventory(self, game_name: str) -> bool:
        self.restore_connection()

        if trade_bot := self._get_bot(game_name):
            return not handle_429_status_code(trade_bot.sell_inventory, self.session)
        return False

    def confirm_all_sell_orders(self) -> None:
        self.restore_connection()

        load_dotenv()
        ConfirmationExecutor(
            os.getenv('IDENTITY_SECRET'),
            self.steam_id,
            self.session
        ).allow_all_confirmations([ConfirmationType.CREATE_LISTING])

        self.console.print(Text("done"))


if __name__ == "__main__":
    TradeUserInterface().run("TradeUI")
