from tools.console import BasicConsole
from tools.file_managers import TempTradeItemManager

from tools.console import ConsoleManager, Command, Param, ParamType
from utils import is_str_int

from rich.text import Text


class ConsoleTempTradeItemManager(BasicConsole):
    def __init__(self, original: TempTradeItemManager):
        self.original = original

    def _register_commands(self, console_manager: ConsoleManager) -> None:
        console_manager.register_command(
            aliases=["add", "add_item"],
            description="Add the item to the temp trade items file",
            action=self.add_item,
            usage="add \"<name>\" (quotation marks are required for names with spaces)"
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
                "-c": Param(
                    description="Вывести количество предметов",
                    action=lambda: len(self.original.items),
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

    def add_item(self, item_name: str) -> Text:
        if self.original.add_item(item_name):
            return Text(f"Добавлено: ('{item_name}')")
        return Text(f"Уже присутствует: ('{item_name}')")

    def delete_item(self, item_name: str) -> Text:
        if self.original.delete_item(item_name):
            return Text(f"'{item_name}' has been deleted")
        return Text(f"No such item", style="red")

    def _print_item(self, item_name: str) -> Text | str | None:
        if item_name in self.original.items:
            return f"Присутствует: [green]{item_name}[/green]"
        return Text(f"No such item", style="red")


if __name__ == "__main__":
    while not is_str_int(app_id := input("Введите ID игры: ")):
        print("Неверный ввод")
    ConsoleTempTradeItemManager(TempTradeItemManager(int(app_id))).run("TempTradeItemManager")
