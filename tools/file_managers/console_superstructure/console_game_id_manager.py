from tools.console import BasicConsole
from tools.file_managers import GameIDManager

from tools.console import ConsoleManager, Command, Param, ParamType

from rich.text import Text


class ConsoleGameIDManager(BasicConsole):
    def __init__(self, original: GameIDManager):
        self.original = original

    def _register_commands(self, console_manager: ConsoleManager) -> None:
        console_manager.register_command(
            aliases=["add", "add_game"],
            description="Add game name, app_id and context_id to the game IDs file",
            action=self.add_item,
            usage="add <name> <app_id> <context_id>"
        )
        console_manager.register_command(
            aliases=["p", "print"],
            description="Print items from file",
            action=self._print_item,
            usage="print <param or item name>",
            params={
                "-all": Param(
                    description="Выводит все элементы",
                    action=lambda: self.original.items,
                    param_type=ParamType.LOGIC
                ),
                "-name": Param(
                    description="Выводит имена элементов",
                    action=lambda: list(self.original.items.keys()),
                    param_type=ParamType.LOGIC
                )
            }
        )
        console_manager.register_command(
            aliases=["del", "delete"],
            description="Delete item from file",
            action=self.delete_item,
            usage="del <name>"
        )

    def add_item(self, game: str, app_id: int, context_id: int) -> Text:
        if self.original.add_item(game, app_id, context_id):
            return Text(f"Добавлено: ('{game}': [{app_id}, {context_id}])")
        return Text(f"Изменено ID: ('{game}': [{app_id}, {context_id}])")

    def delete_item(self, game: str) -> Text:
        if self.original.delete_item(game):
            return Text(f"'{game}' has been deleted")
        return Text(f"No such game", style="red")

    def _print_item(self, item_name: str) -> Text | None:
        if item_value := self.original.items.get(item_name):
            return Text(f"{item_name}: {item_value}")
        return Text(f"No such item")


if __name__ == "__main__":
    ConsoleGameIDManager(GameIDManager()).run("GameIDManager")
