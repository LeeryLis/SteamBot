from abc import ABC, abstractmethod

from tools.file_store import FileStore, FileStoreType

from _root import project_root


class BasicFileManager(ABC):
    def __init__(self, file_name: str) -> None:
        self.file_path = project_root / f'data/{file_name}'
        self.file_store = FileStore.from_type(FileStoreType.JSON)
        self.items = {}
        self.load_items()

    def load_items(self) -> None:
        self.items = self.file_store.load(self.file_path, default={})

    @abstractmethod
    def add_item(self, *args, **kwargs) -> bool:
        """
        Абстрактный метод добавления элемента
        """
        pass

    @abstractmethod
    def delete_item(self, *args, **kwargs) -> bool:
        """
        Абстрактный метод удаления элемента
        """
        pass

    def save_items(self) -> None:
        self.file_store.save(self.file_path, self.items)
