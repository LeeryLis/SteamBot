from typing import Iterable
import enum
from typing import NamedTuple

import requests
import time

from steam_lib.guard import generate_confirmation_key, generate_device_id


class ConfirmationTag:
    CONF = 'conf'
    DETAILS = 'details'
    ALLOW = 'allow'
    CANCEL = 'cancel'

class ConfirmationType(enum.IntEnum):
    TRADE = 2  # Send offer and accept
    CREATE_LISTING = 3
    CHANGE_PHONE_NUMBER = 5
    CONFIRM = 6  # I saw in the mail change
    REGISTER_API_KEY = 9
    BUY_LISTING = 12


class Confirmation(NamedTuple):
    type: ConfirmationType
    type_name: str
    id: str
    creator_id: str
    nonce: str
    creation_time: str
    cancel: str
    accept: str
    icon: str
    multi: bool
    headline: str
    summary: dict
    warn: None

    def __str__(self) -> str:
        if not self.summary or not self.summary[0]:
            if not self.headline:
                return f'Unknown {self.type.name}'
            return self.headline
        return f'Confirmation: {self.summary[0]}'

    def __repr__(self) -> str:
        if not self.summary or not self.summary[0]:
            if not self.headline:
                return f'Unknown {self.type.name}'
            return self.headline
        return f'Confirmation: {self.summary[0]}'

class SteamUrl:
    API = 'https://api.steampowered.com'
    COMMUNITY = 'https://steamcommunity.com'
    STORE = 'https://store.steampowered.com'
    LOGIN = 'https://login.steampowered.com'


class ConfirmationExecutor:
    CONF_URL = SteamUrl.COMMUNITY + '/mobileconf'

    def __init__(self, identity_secret: str, steam_id: str,
                 session: requests.Session) -> None:
        self.steam_id = steam_id
        self.identity_secret = identity_secret
        self.session = session
        self.was_login_executed = False

        self.headers = {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/128.0.0.0 Safari/537.36 OPR/114.0.0.0 (Edition Yx 08)'
            ),
            'Accept': '*/*',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br, zstd',
            'X-Requested-With': 'XMLHttpRequest',
            'Connection': 'keep-alive',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin'
        }

    def respond_to_confirmation(self, confirmation: Confirmation,
                                cancel: bool = False) -> bool:
        tag = ConfirmationTag.ALLOW if cancel is False\
            else ConfirmationTag.CANCEL
        params = self._create_confirmation_params(tag)
        params['op'] = tag
        params['ck'] = confirmation.nonce
        params['cid'] = confirmation.id
        headers = {'X-Requested-With': 'XMLHttpRequest'}
        response = self.session.get(
            self.CONF_URL + '/ajaxop', params=params, headers=headers)
        try:
            status = response.json()['success']
        except requests.exceptions.JSONDecodeError:
            status = False
        return status

    def respond_to_confirmations(self, confirmations: Iterable[Confirmation],
                                 cancel: bool = False) -> bool:
        tag = ConfirmationTag.ALLOW if cancel is False\
            else ConfirmationTag.CANCEL
        params = self._create_confirmation_params(tag)
        params['op'] = tag
        params['ck[]'] = [i.nonce for i in confirmations]
        params['cid[]'] = [i.id for i in confirmations]
        headers = {'X-Requested-With': 'XMLHttpRequest'}
        response = self.session.post(
            self.CONF_URL + '/multiajaxop', data=params, headers=headers)
        try:
            status = response.json()['success']
        except requests.exceptions.JSONDecodeError:
            status = False
        return status

    def get_confirmations(self) -> list[Confirmation]:
        confirmations: list[Confirmation] = []
        confirmations_page = self._fetch_confirmations_page()
        for conf in confirmations_page.json().get('conf'):
            confirmations.append(Confirmation(
                type=ConfirmationType(int(conf['type'])),
                type_name=conf['type_name'],
                id=conf['id'],
                creator_id=conf['creator_id'],
                nonce=conf['nonce'],
                creation_time=conf['creation_time'],
                cancel=conf['cancel'],
                accept=conf['accept'],
                icon=conf['icon'],
                multi=conf['multi'],
                headline=conf['headline'],
                summary=conf['summary'],
                warn=conf['warn']
            ))
        return confirmations

    def _fetch_confirmations_page(self) -> requests.Response:
        url = self.CONF_URL + '/getlist'
        tag = ConfirmationTag.CONF
        params = self._create_confirmation_params(tag)
        headers = {'X-Requested-With': 'com.valvesoftware.android.steam.community'}
        return self.session.get(url, params=params, headers=headers)

    def _create_confirmation_params(self, tag: str) -> dict[str, str]:
        timestamp = int(time.time())
        confirmation_key = generate_confirmation_key(
            self.identity_secret, tag)
        android_id = generate_device_id(self.steam_id)  # os.getenv('DEVICE_ID')
        params = {
            'p': android_id,
            'a': self.steam_id,
            'k': confirmation_key,
            't': timestamp,
            'm': 'react',
            'tag': tag
        }
        return params

    def allow_buy_order_confirmation(self)\
            -> bool:
        types = [ConfirmationType.BUY_LISTING]
        confirmations = self.get_confirmations()
        for confirmation in confirmations:
            if confirmation.type in types:
                return self.respond_to_confirmation(confirmation)
        return False

    def allow_all_confirmations(self, types: Iterable[ConfirmationType])\
            -> bool:
        confirmations = self.get_confirmations()
        selected_confirmations = []
        for confirmation in confirmations:
            if confirmation.type in types:
                selected_confirmations.append(confirmation)
        return self.respond_to_confirmations(selected_confirmations)
