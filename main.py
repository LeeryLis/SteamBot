from rich.text import Text

from tools.console import BasicConsole

from tools.console import ConsoleManager, Command
from tools.file_managers import ItemManager, TradeItemManager, GameIDManager, TempTradeItemManager
from tools.file_managers import ConsoleGameIDManager, ConsoleItemManager,\
    ConsoleTradeItemManager, ConsoleTempTradeItemManager

from bot import TradeUserInterface

class App(BasicConsole):
    def _register_commands(self, console_manager: ConsoleManager) -> None:
        console_manager.register_command(
            aliases=["games"],
            description="Вывести названия всех доступных для взаимодействия игр",
            action=lambda: list(self._get_available_games())
        )
        console_manager.register_command(
            aliases=["gm", "game_id_manager"],
            description="Интерфейс взаимодействия с файлом, содержащим названия игр Steam с app_id и context_id",
            action=lambda: ConsoleGameIDManager(GameIDManager()).run("GameIDManager"),
            print_result=False
        )
        console_manager.register_command(
            aliases=["ui", "trade_ui"],
            description="Интерфейс взаимодействия с торговлей в Steam",
            action=lambda: TradeUserInterface().run("TradeUI"),
            print_result=False
        )
        console_manager.register_command(
            aliases=["im", "item_manager"],
            description="Интерфейс взаимодействия с файлом, содержащим ID предметов Steam",
            action=self._run_item_manager,
            usage="im <game>",
            print_result=False
        )
        console_manager.register_command(
            aliases=["tim", "trade_item_manager"],
            description="Интерфейс взаимодействия с файлом предметов Steam, выбранных для автоматической торговли",
            action=self._run_trade_item_manager,
            usage="tim <game>",
            print_result=False
        )
        console_manager.register_command(
            aliases=["ttim", "temp_trade_item_manager"],
            description="Интерфейс взаимодействия с файлом предметов Steam, для которых "
                        "не будут обновляться 'sell order'",
            action=self._run_temp_trade_item_manager,
            usage="ttim <game>",
            print_result=False
        )

    def _run_item_manager(self, game_name: str) -> Text | None:
        available_games = self._get_available_games()
        if game := available_games.get(game_name):
            ConsoleItemManager(ItemManager(game[0])).run("ItemManager")
        else:
            return Text(f"Игра '{game_name}' не поддерживается. Доступные: {list(available_games.keys())}")

    def _run_trade_item_manager(self, game_name: str) -> Text | None:
        available_games = self._get_available_games()
        if game := available_games.get(game_name):
            ConsoleTradeItemManager(TradeItemManager(game[0])).run("TradeItemManager")
        else:
            return Text(f"Игра '{game_name}' не поддерживается. Доступные: {list(available_games.keys())}")

    def _run_temp_trade_item_manager(self, game_name: str) -> Text | None:
        available_games = self._get_available_games()
        if game := available_games.get(game_name):
            ConsoleTempTradeItemManager(TempTradeItemManager(game[0])).run("TempTradeItemManager")
        else:
            return Text(f"Игра '{game_name}' не поддерживается. Доступные: {list(available_games.keys())}")

    def _get_available_games(self) -> dict[str, list[int]]:
        return GameIDManager().items


if __name__ == "__main__":
    App().run("MainApp")
