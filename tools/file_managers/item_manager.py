from tools.file_managers import BasicFileManager


class ItemManager(BasicFileManager):
    def __init__(self, app_id: int, file_name: str = "items/{}.json") -> None:
        """
        :param app_id: ID игры в Steam (нужно для разделения торговли по играм)
        :param file_name: Имя файла в директории data/
        """
        super().__init__(file_name.format(app_id))
        self.app_id = app_id

    def add_item(self, item_name: str, item_name_id: int) -> bool:
        if item_name not in self.items:
            result = True
        else:
            result = False
        self.items[item_name] = item_name_id
        self.save_items()
        return result

    def delete_item(self, game: str) -> bool:
        if not self.items.get(game):
            return False

        del self.items[game]
        self.save_items()
        return True
