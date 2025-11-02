from tools.console import BasicConsole, command
from tools.file_managers import ItemManager, TradeItemManager

from utils import is_str_int

from rich.text import Text
from rich.console import Console


class ConsoleItemManager(BasicConsole):
    def __init__(self, original: ItemManager):
        self.original = original
        self.console = Console()

        self.trade_item_manager = TradeItemManager(self.original.app_id)

    def get_item_names_without_id(self) -> list[str]:
        return list(filter(
            lambda item_name: self.original.items.get(item_name) is None,
            self.trade_item_manager.items.keys()
        ))

    @command(
        aliases=["add", "add_item"],
        description="Add the item and id to the items file",
        usage="add \"<name>\" <id> (quotation marks are required for names with spaces)"
    )
    def add_item(self, item_name: str, item_name_id: int) -> None:
        if self.original.add_item(item_name, item_name_id):
            self.console.print(Text(f"Добавлено: ('{item_name}': {item_name_id})"))
            return
        self.console.print(Text(f"Изменено ID: ('{item_name}': {item_name_id})"))

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
            "print_names": (["-name"], "Вывести имена элементов"),
            "print_noid": (["-noid"], "Вывести имена элементов из trade_items, для которых в items не указано ID")
        }
    )
    def _print_item(
            self, item_name: str = "",
            print_all: bool = False, print_names: bool = False, print_noid: bool = False
    ) -> None:
        if print_all:
            self.console.print(self.original.items)
            return

        if print_names:
            self.console.print(list(self.original.items.keys()))
            return

        if print_noid:
            self.console.print(self.get_item_names_without_id())
            return

        if item_value := self.original.items.get(item_name):
            self.console.print(f"{item_name}: {item_value}")
            return
        self.console.print(Text(f"No such item"), style="red")


if __name__ == "__main__":
    while not is_str_int(app_id := input("Введите ID игры: ")):
        print("Неверный ввод")
    ConsoleItemManager(ItemManager(int(app_id))).run("ItemManager")
