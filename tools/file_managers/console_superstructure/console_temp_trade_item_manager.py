from tools.console import BasicConsole, command
from tools.file_managers import TempTradeItemManager

from utils import is_str_int

from rich.text import Text
from rich.console import Console


class ConsoleTempTradeItemManager(BasicConsole):
    def __init__(self, original: TempTradeItemManager):
        self.original = original
        self.console = Console()

    @command(
        aliases=["add", "add_item"],
        description="Add the item to the temp trade items file",
        usage="add \"<name>\" (quotation marks are required for names with spaces)"
    )
    def add_item(self, item_name: str) -> None:
        if self.original.add_item(item_name):
            self.console.print(Text(f"Добавлено: ('{item_name}')"))
            return
        self.console.print(Text(f"Уже присутствует: ('{item_name}')"))

    @command(
        aliases=["del", "delete"],
        description="Delete item from file",
        usage="del \"<name>\" (quotation marks are required for names with spaces)"
    )
    def delete_item(self, item_name: str) -> None:
        if self.original.delete_item(item_name):
            self.console.print(Text(f"'{item_name}' has been deleted"))
            return
        self.console.print(Text(f"No such item", style="red"))

    @command(
        aliases=["p", "print"],
        description="Вывести информацию",
        flags={
            "print_all": (["-all"], "Вывести все элементы"),
            "print_count": (["-c"], "Вывести количество элементов")
        }
    )
    def _print_item(self, item_name: str = "", print_all: bool = False, print_count: bool = False) -> None:
        if print_all:
            self.console.print(self.original.items)
            return

        if print_count:
            self.console.print(len(self.original.items))
            return

        if item_name in self.original.items:
            self.console.print(f"Присутствует: [green]{item_name}[/green]")
            return
        self.console.print(Text(f"No such item"), style="red")


if __name__ == "__main__":
    while not is_str_int(app_id := input("Введите ID игры: ")):
        print("Неверный ввод")
    ConsoleTempTradeItemManager(TempTradeItemManager(int(app_id))).run("TempTradeItemManager")
