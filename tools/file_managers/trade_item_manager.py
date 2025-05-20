from tools.file_managers import BasicFileManager


class TradeItemManager(BasicFileManager):
    def __init__(self, app_id: int, file_name: str = "trade_items/{}.json") -> None:
        """
        :param app_id: ID игры в Steam (нужно для разделения торговли по играм)
        :param file_name: Имя файла в директории data/
        """
        super().__init__(file_name.format(app_id))

    def add_item(self, item_name: str, max_count: int) -> bool:
        if item_name not in self.items:
            result = True
        else:
            result = False
        self.items[item_name] = max_count
        self.save_items()
        return result

    def delete_item(self, item_name: str) -> bool:
        item_value = self.items.get(item_name)
        if not item_value and item_value != 0:
            return False

        del self.items[item_name]
        self.save_items()
        return True

    def set_zero_item(self, item_name: str) -> bool:
        if item_name not in self.items:
            return False
        self.items[item_name] = 0
        self.save_items()
        return True

    def get_zero_items(self) -> dict:
        return {key: value for key, value in self.items.items() if value == 0}
