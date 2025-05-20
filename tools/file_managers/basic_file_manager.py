import json
import os
from abc import ABC, abstractmethod

from _root import project_root


class BasicFileManager(ABC):
    def __init__(self, file_name: str) -> None:
        self.file_path = project_root / f'data/{file_name}'
        self.items = {}
        self.load_items()

    def load_items(self) -> None:
        if os.path.exists(self.file_path):
            with open(self.file_path, 'r', encoding='utf-8') as file:
                self.items = json.load(file)
        else:
            self.items = {}

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
        dir_path = os.path.dirname(self.file_path)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        with open(self.file_path, 'w', encoding='utf-8') as file:
            json.dump(self.items, file, ensure_ascii=False, indent=4)
