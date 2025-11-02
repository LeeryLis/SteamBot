import os
import requests
from bs4 import BeautifulSoup

from tools.rate_limiter import rate_limited
from utils import handle_status_codes_using_attempts
from tools import BasicLogger

from enums import Urls
from utils.exceptions import TooManyRequestsError


class Account(BasicLogger):
    """
        Все функции, связанные так или иначе с аккаунтом, но не требующие
        выбора определённой игры
    """
    def __init__(self) -> None:
        super().__init__(
            logger_name=f"{self.__class__.__name__}",
            dir_specify="account",
            file_name=f"{self.__class__.__name__}"
        )

    @handle_status_codes_using_attempts()
    @rate_limited(1)
    def get_account_page(self, session: requests.Session) -> requests.Response:
        url = Urls.ACCOUNT
        headers = {
            'Referer': url,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:143.0) "
                          "Gecko/20100101 Firefox/143.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9"
        }

        response = session.get(url, headers=headers)

        if response.status_code != 200:
            self.logger.error(
                f"Ошибка при получении страницы sell orders: "
                f"{response.status_code} {response.reason}")
            if response.status_code == 429:
                raise TooManyRequestsError()

        return response

    def get_account_balance(self, session: requests.Session) -> list[int] | None:
        response = self.get_account_page(session)

        if response.status_code != 200:
            return None

        result = [0, 0, 0]

        soup = BeautifulSoup(response.content, "html.parser")
        account_rows = soup.findAll("div", class_="accountRow accountBalance")

        result[0] = float(account_rows[0].get_text(strip=True).replace(",", ".").split()[0])
        try:
            result[1] = float(account_rows[1].get_text(strip=True).replace(",", ".").split()[0])
        except IndexError:
            pass
        
        result[2] = result[0] + result[1]

        return result
