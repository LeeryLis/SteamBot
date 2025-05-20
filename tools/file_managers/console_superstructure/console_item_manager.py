from tools.console import BasicConsole
from tools.file_managers import ItemManager, TradeItemManager

from tools.console import ConsoleManager, Command, Param, ParamType
from utils import is_str_int

from rich.text import Text


class ConsoleItemManager(BasicConsole):
    def __init__(self, original: ItemManager):
        self.original = original

        self.trade_item_manager = TradeItemManager(self.original.app_id)

    def _register_commands(self, console_manager: ConsoleManager) -> None:
        console_manager.register_command(
            aliases=["add", "add_item"],
            description="Add the item and id to the items file",
            action=self.add_item,
            usage="add \"<name>\" <id> (quotation marks are required for names with spaces)"
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
                "-noid": Param(
                    description="Выводит имена элементов из trade_items, для которых в items не указано ID",
                    action=lambda: self.get_item_names_without_id(),
                    param_type=ParamType.LOGIC
                )
            }
        )
        console_manager.register_command(
            aliases=["del", "delete"],
            description="Delete item from file",
            action=self.delete_item,
            usage="del \"<name>\" (quotation marks are required for names with spaces)"
        )

    def get_item_names_without_id(self) -> list[str]:
        return list(filter(
            lambda item_name: self.original.items.get(item_name) is None,
            self.trade_item_manager.items.keys()
        ))

    def add_item(self, item_name: str, item_name_id: int) -> Text:
        if self.original.add_item(item_name, item_name_id):
            return Text(f"Добавлено: ('{item_name}': {item_name_id})")
        return Text(f"Изменено ID: ('{item_name}': {item_name_id})")

    def delete_item(self, item_name: str) -> Text:
        if self.original.delete_item(item_name):
            return Text(f"'{item_name}' has been deleted")
        return Text(f"No such item", style="red")

    def _print_item(self, item_name: str) -> Text | None:
        if item_value := self.original.items.get(item_name):
            return Text(f"{item_name}: {item_value}")
        return Text(f"No such item")


if __name__ == "__main__":
    while not is_str_int(app_id := input("Введите ID игры: ")):
        print("Неверный ввод")
    ConsoleItemManager(ItemManager(int(app_id))).run("ItemManager")
