import os
import json

from tools.file_managers import BasicFileManager


class TempTradeItemManager(BasicFileManager):
    def __init__(self, app_id: int, file_name: str = "temp_trade_items/{}.json") -> None:
        """
        :param app_id: ID игры в Steam (нужно для разделения торговли по играм)
        :param file_name: Имя файла в директории data/
        """
        super().__init__(file_name.format(app_id))
        self.items = []
        self.load_items()

    def load_items(self) -> None:
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r', encoding='utf-8') as file:
                self.items = json.load(file)
        else:
            self.items = []

    def add_item(self, item_name: str) -> bool:
        if item_name in self.items:
            return False
        self.items.append(item_name)
        self.save_items()
        return True

    def delete_item(self, item_name: str) -> bool:
        try:
            self.items.remove(item_name)
            self.save_items()
            return True
        except ValueError:
            return False
