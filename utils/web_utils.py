import time

import logging
import requests
from requests.exceptions import ConnectionError, ReadTimeout, Timeout, SSLError
from rich.console import Console
from datetime import datetime
from utils.exceptions import TooManyRequestsError


base_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) Gecko/20100101 Firefox/143.0",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9"
}

def api_request(
        session: requests.Session,
        method: str,
        url: str,
        *,
        headers: dict = None,
        params: dict = None,
        data: dict = None,
        json_data: dict = None,
        max_retries: int = 3,
        backoff: float = 2.0,
        check_status: bool = True,
        logger: logging.Logger = None
) -> requests.Response:
    final_headers = base_headers.copy()
    if headers:
        final_headers.update(headers)

    attempt = 0
    while attempt < max_retries:
        try:
            response = session.request(
                method,
                url,
                headers=final_headers,
                params=params,
                data=data,
                json=json_data,
                timeout=15
            )

            if check_status and response.status_code != 200:
                logger.error(f"Ошибка при обращении к {url}:"
                             f"{response.status_code} {response.reason}")
                if response.status_code == 429:
                    raise TooManyRequestsError()
            return response
        except (ConnectionError, ReadTimeout, Timeout, SSLError) as e:
            attempt += 1
            logger.warning(f"Request failed (attempt {attempt}/{max_retries}) "
                           f"for {url}: {e}. Retrying in {backoff} seconds")
            time.sleep(backoff)

    raise RuntimeError(f"Не удалось выполнить запрос к {url} после {max_retries} попыток")

def handle_429_status_code(func: callable, *args, **kwargs) -> bool:
    try:
        func(*args, **kwargs)
        return False
    except TooManyRequestsError as ex:
        Console().print(
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
            f"Ошибка: {ex}"
        )
        return True
