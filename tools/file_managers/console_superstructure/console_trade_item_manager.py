from tools.console import BasicConsole, command
from tools.file_managers import TradeItemManager

from utils import is_str_int

from rich.text import Text
from rich.console import Console


class ConsoleTradeItemManager(BasicConsole):
    def __init__(self, original: TradeItemManager):
        self.original = original
        self.console = Console()

    @command(
        aliases=["add", "add_item"],
        description="Add the item and count to the trade items file",
        usage="add \"<name>\" <count> (quotation marks are required for names with spaces)"
    )
    def add_item(self, item_name: str, count: int) -> None:
        if self.original.add_item(item_name, count):
            self.console.print(Text(f"Добавлено: ('{item_name}': {count})"))
            return
        self.console.print(Text(f"Изменено количество: ('{item_name}': {count})", style="yellow"))

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

    def get_count_zero_items(self) -> int:
        zero_items = self.get_zero_items()
        if isinstance(zero_items, dict):
            return len(zero_items)
        return 0

    @command(
        aliases=["p", "print"],
        description="Вывести информацию",
        flags={
            "print_all": (["-all"], "Вывести все элементы"),
            "print_names": (["-name"], "Выводит имена элементов"),
            "print_zero": (["-zero"], "Выводит имена всех элементов с нулевым значением"),
            "print_count": (["-c"], "Вывести количество элементов"),
            "print_count_zero": (["-cz"], "Вывести количество предметов со значением ноль"),
            "print_count_not_zero": (["-cnz"], "Вывести количество предметов со значением не ноль")
        }
    )
    def _print_item(
            self, item_name: str = "",
            print_all: bool = False, print_names: bool = False, print_zero: bool = False,
            print_count: bool = False, print_count_zero: bool = False, print_count_not_zero: bool = False
    ) -> None:
        if print_all:
            self.console.print(self.original.items)
            return

        if print_names:
            self.console.print(list(self.original.items.keys()))
            return

        if print_zero:
            self.console.print(self.get_zero_items())
            return

        if print_count:
            self.console.print(len(self.original.items.keys()))
            return

        if print_count_zero:
            self.console.print(self.get_count_zero_items())
            return

        if print_count_not_zero:
            self.console.print(len(self.original.items.keys()) - self.get_count_zero_items())
            return

        item_value = self.original.items.get(item_name)
        if item_value or item_value == 0:
            self.console.print(f"{item_name}: {item_value}")
            return
        self.console.print(Text(f"No such item"), style="red")

    @command(
        aliases=["z", "zero"],
        description="Set item count to zero",
        usage="zero \"<name>\" (quotation marks are required for names with spaces)"
    )
    def set_zero_item(self, item_name: str) -> None:
        if self.original.set_zero_item(item_name):
            self.console.print(Text(f"Количество установлено на 0: ('{item_name}': 0)"))
            return
        self.console.print(Text("No such item", style="red"))

    def get_zero_items(self) -> Text | dict:
        if zero_items := self.original.get_zero_items():
            return zero_items
        return Text("No items with value zero")


if __name__ == "__main__":
    while not is_str_int(app_id := input("Введите ID игры: ")):
        print("Неверный ввод")
    ConsoleTradeItemManager(TradeItemManager(int(app_id))).run("TradeItemManager")
