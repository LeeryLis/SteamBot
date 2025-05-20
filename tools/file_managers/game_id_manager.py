from tools.file_managers import BasicFileManager


class GameIDManager(BasicFileManager):
    def __init__(self, file_name: str = "game_IDs.json") -> None:
        """
        :param file_name: Имя файла в директории data/
        """
        super().__init__(file_name)

    def add_item(self, game: str, app_id: int, context_id: int) -> bool:
        if game not in self.items:
            result = True
        else:
            result = False
        self.items[game] = (app_id, context_id)
        self.save_items()
        return result

    def delete_item(self, game: str) -> bool:
        if not self.items.get(game):
            return False

        del self.items[game]
        self.save_items()
        return True
