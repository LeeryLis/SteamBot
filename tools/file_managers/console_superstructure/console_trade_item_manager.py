from tools.console import BasicConsole
from tools.file_managers import TradeItemManager

from tools.console import ConsoleManager, Command, Param, ParamType
from utils import is_str_int

from rich.text import Text


class ConsoleTradeItemManager(BasicConsole):
    def __init__(self, original: TradeItemManager):
        self.original = original

    def _register_commands(self, console_manager: ConsoleManager) -> None:
        console_manager.register_command(
            aliases=["add", "add_item"],
            description="Add the item and count to the trade items file",
            action=self.add_item,
            usage="add \"<name>\" <count> (quotation marks are required for names with spaces)"
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
                ),
                "-zero": Param(
                    description="Выводит имена всех элементов с нулевым значением",
                    action=lambda: self.get_zero_items(),
                    param_type=ParamType.LOGIC
                ),
                "-c": Param(
                    description="Вывести количество предметов",
                    action=lambda: len(self.original.items.keys()),
                    param_type=ParamType.LOGIC
                ),
                "-cz": Param(
                    description="Вывести количество предметов со значением ноль",
                    action=lambda: self.get_count_zero_items(),
                    param_type=ParamType.LOGIC
                ),
                "-cnz": Param(
                    description="Вывести количество предметов со значением не ноль",
                    action=lambda: len(self.original.items.keys()) - self.get_count_zero_items(),
                    param_type=ParamType.LOGIC
                )
            }
        )
        console_manager.register_command(
            aliases=["z", "zero"],
            description="Set item count to zero",
            action=self.set_zero_item,
            usage="zero \"<name>\" (quotation marks are required for names with spaces)"
        )
        console_manager.register_command(
            aliases=["del", "delete"],
            description="Delete item from file",
            action=self.delete_item,
            usage="del \"<name>\" (quotation marks are required for names with spaces)"
        )

    def add_item(self, item_name: str, count: int) -> Text:
        if self.original.add_item(item_name, count):
            return Text(f"Добавлено: ('{item_name}': {count})")
        return Text(f"Изменено количество: ('{item_name}': {count})")

    def delete_item(self, item_name: str) -> Text:
        if self.original.delete_item(item_name):
            return Text(f"'{item_name}' has been deleted")
        return Text(f"No such item", style="red")

    def get_count_zero_items(self) -> int:
        zero_items = self.get_zero_items()
        if isinstance(zero_items, dict):
            return len(zero_items)
        return 0

    def _print_item(self, item_name: str) -> Text | None:
        item_value = self.original.items.get(item_name)
        if item_value or item_value == 0:
            return Text(f"{item_name}: {item_value}")
        return Text(f"No such item")

    def set_zero_item(self, item_name: str) -> Text:
        if self.original.set_zero_item(item_name):
            return Text(f"Количество установлено на 0: ('{item_name}': 0)")
        return Text("No such item", style="red")

    def get_zero_items(self) -> Text | dict:
        if zero_items := self.original.get_zero_items():
            return zero_items
        return Text("No items with value zero")


if __name__ == "__main__":
    while not is_str_int(app_id := input("Введите ID игры: ")):
        print("Неверный ввод")
    ConsoleTradeItemManager(TradeItemManager(int(app_id))).run("TradeItemManager")
