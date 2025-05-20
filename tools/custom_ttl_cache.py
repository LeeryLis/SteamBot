import os
import cachetools
import dill
from typing import Optional

class CustomTTLCache(cachetools.TTLCache):
    def __init__(self, maxsize: int, ttl: int) -> None:
        super().__init__(maxsize, ttl)

    def save_cache(self, filename: str) -> None:
        cache_dir = os.path.dirname(filename)
        os.makedirs(cache_dir, exist_ok=True)
        with open(filename, 'wb') as f:
            dill.dump(self, f)

    @classmethod
    def load_cache(cls, filename: str, maxsize: int, ttl: int) -> Optional['CustomTTLCache']:
        try:
            with open(filename, 'rb') as f:
                return dill.load(f)
        except FileNotFoundError:
            return cls(maxsize, ttl)
