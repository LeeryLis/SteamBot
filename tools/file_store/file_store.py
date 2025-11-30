import json
import os
import pickle
from pathlib import Path
from typing import Callable, Any, Optional

from tools.file_store import FileStoreType


class FileStore:
    def __init__(
            self,
            serializer: Callable[[Any, Any], None],
            deserializer: Callable[[Any], Any],
            binary: bool
    ):
        self.serializer = serializer
        self.deserializer = deserializer
        self.binary = binary

    @staticmethod
    def from_type(store_type: FileStoreType) -> 'FileStore':
        if store_type is FileStoreType.PICKLE:
            return FileStore(
                serializer=lambda obj, f: pickle.dump(obj, f),
                deserializer=lambda f: pickle.load(f),
                binary=True
            )

        if store_type is FileStoreType.JSON:
            return FileStore(
                serializer=lambda obj, f: json.dump(
                    obj, f, ensure_ascii=False, indent=4
                ),
                deserializer=lambda f: json.load(f),
                binary=False
            )

        raise ValueError(f"Unknown FileStoreType: {store_type}")

    @staticmethod
    def _ensure_dir(path: Path) -> None:
        dir_path = path.parent
        if not dir_path.exists():
            dir_path.mkdir(parents=True, exist_ok=True)

    def save(self, path: str | Path, obj: Any) -> bool:
        path = Path(path)
        try:
            self._ensure_dir(path)
            mode = "wb" if self.binary else "w"
            encoding = None if self.binary else "utf-8"

            with open(path, mode, encoding=encoding) as f:
                self.serializer(obj, f)
            return True
        except Exception as e:
            print(f"File save failed for {path}: {e}")
            return False

    def load(self, path: str | Path, default: Optional[Any] = None) -> Any:
        path = Path(path)
        if not path.exists():
            return default
        try:
            mode = "rb" if self.binary else "r"
            encoding = None if self.binary else "utf-8"

            with open(path, mode, encoding=encoding) as f:
                return self.deserializer(f)
        except Exception as e:
            print(f"File load failed for {path}: {e}")
            return default
