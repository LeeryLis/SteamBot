import os
import logging
from logging.handlers import RotatingFileHandler

from _root import project_root


class BasicLogger:
    def __init__(self, logger_name: str, dir_specify: str, file_name: str) -> None:
        # self.logger = logging.getLogger(f"{self.__class__.__name__}{self.app_id}")
        self.logger = logging.getLogger(f"{logger_name}")
        if not self.logger.handlers:
            # file_path = f"{project_root}/logs/{self.app_id}/{self.__class__.__name__}.log"
            file_path = f"{project_root}/logs/{dir_specify}/{file_name}.log"
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            handler = RotatingFileHandler(
                file_path,
                encoding="utf-8",
                maxBytes=1024 * 1024,
                backupCount=5
            )
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.DEBUG)