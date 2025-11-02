from tools.console import BasicConsole, command
from tools.file_managers import GameIDManager

from rich.text import Text
from rich.console import Console


class ConsoleGameIDManager(BasicConsole):
    def __init__(self, original: GameIDManager):
        self.original = original
        self.console = Console()

    @command(
        aliases=["add", "add_game"],
        description="Add game name, app_id and context_id to the game IDs file",
        usage="add <name> <app_id> <context_id>"
    )
    def add_item(self, game: str, app_id: int, context_id: int) -> None:
        if self.original.add_item(game, app_id, context_id):
            self.console.print(Text(f"Добавлено: ('{game}': [{app_id}, {context_id}])"))
            return
        self.console.print(Text(f"Изменено ID: ('{game}': [{app_id}, {context_id}])"))

    @command(
        aliases=["del", "delete"],
        description="Delete item from file",
        usage="del \"<name>\" (quotation marks are required for names with spaces)"
    )
    def delete_item(self, game: str) -> None:
        if self.original.delete_item(game):
            self.console.print(Text(f"'{game}' has been deleted"))
            return
        self.console.print(Text(f"No such item", style="red"))

    @command(
        aliases=["p", "print"],
        description="Вывести информацию",
        flags={
            "print_all": (["-all"], "Вывести все элементы"),
            "print_names": (["-name"], "Вывести имена элементов")
        }
    )
    def _print_item(self, item_name: str = "", print_all: bool = False, print_names: bool = False) -> None:
        if print_all:
            self.console.print(self.original.items)
            return

        if print_names:
            self.console.print(list(self.original.items.keys()))
            return

        if item_value := self.original.items.get(item_name):
            self.console.print(f"{item_name}: {item_value}")
            return
        self.console.print(Text(f"No such item"), style="red")


if __name__ == "__main__":
    ConsoleGameIDManager(GameIDManager()).run("GameIDManager")
