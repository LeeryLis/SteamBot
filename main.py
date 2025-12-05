from rich.text import Text
from rich.console import Console

from tools.console import BasicConsole, command

from tools.file_managers import ItemManager, TradeItemManager, GameIDManager, TempTradeItemManager
from tools.file_managers import ConsoleGameIDManager, ConsoleItemManager,\
    ConsoleTradeItemManager, ConsoleTempTradeItemManager

from bot import TradeUserInterface

class App(BasicConsole):
    def __init__(self) -> None:
        self.console = Console()

    @command(
        aliases=["im", "item_manager"],
        description="Интерфейс взаимодействия с файлом, содержащим ID предметов Steam",
        usage="im <game>"
    )
    def _run_item_manager(self, game_name: str) -> None:
        available_games = self._get_available_games(False)
        if game := available_games.get(game_name):
            ConsoleItemManager(ItemManager(game[0])).run("ItemManager")
        else:
            self.console.print(Text(f"Игра '{game_name}' не поддерживается. Доступные: {list(available_games.keys())}"))

    @command(
        aliases=["tim", "trade_item_manager"],
        description="Интерфейс взаимодействия с файлом предметов Steam, выбранных для автоматической торговли",
        usage="tim <game>"
    )
    def _run_trade_item_manager(self, game_name: str) -> None:
        available_games = self._get_available_games(False)
        if game := available_games.get(game_name):
            ConsoleTradeItemManager(TradeItemManager(game[0])).run("TradeItemManager")
        else:
            self.console.print(Text(f"Игра '{game_name}' не поддерживается. Доступные: {list(available_games.keys())}"))

    # @command(
    #     aliases=["ttim", "temp_trade_item_manager"],
    #     description="Интерфейс взаимодействия с файлом предметов Steam, для которых "
    #                 "не будут обновляться 'sell order'",
    #     usage="ttim <game>"
    # )
    def _run_temp_trade_item_manager(self, game_name: str) -> None:
        available_games = self._get_available_games(False)
        if game := available_games.get(game_name):
            ConsoleTempTradeItemManager(TempTradeItemManager(game[0])).run("TempTradeItemManager")
        else:
            self.console.print(Text(f"Игра '{game_name}' не поддерживается. Доступные: {list(available_games.keys())}"))

    @command(
        aliases=["games"],
        description="Вывести названия всех доступных для взаимодействия игр"
    )
    def _get_available_games(self, print_result: bool = True) -> dict[str, list[int]]:
        result = GameIDManager().items
        if print_result:
            self.console.print(list(result))
        return result

    @command(
        aliases=["gm", "game_id_manager"],
        description="Интерфейс взаимодействия с файлом, содержащим названия игр Steam с app_id и context_id"
    )
    def _run_game_id_manager(self):
        ConsoleGameIDManager(GameIDManager()).run("GameIDManager")

    @command(
        aliases=["ui", "trade_ui"],
        description="Интерфейс взаимодействия с торговлей в Steam"
    )
    def _run_trade_user_interface(self):
        TradeUserInterface().run("TradeUI")


if __name__ == "__main__":
    App().run("MainApp")
