import base64
import rsa

import requests

from .guard import generate_one_time_code
from enums import Urls


class IAuthenticationServiceEndpoint:
    SERVICE = Urls.API + '/IAuthenticationService'
    GetPasswordRSAPublicKey = SERVICE + '/GetPasswordRSAPublicKey/v1'
    BeginAuthSessionViaCredentials = SERVICE +\
        '/BeginAuthSessionViaCredentials/v1'
    UpdateAuthSessionWithSteamGuardCode = SERVICE +\
        '/UpdateAuthSessionWithSteamGuardCode/v1'
    PollAuthSessionStatus = SERVICE + '/PollAuthSessionStatus/v1'


class LoginExecutor:

    def __init__(self, username: str, password: str,
                 shared_secret: str, session: requests.Session) -> None:
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.steam_id = ''  # will be added after login requests
        self.session = session

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

    def login(self) -> str:
        self.session.get(Urls.COMMUNITY)  # to get a cookies
        rsa_key, rsa_timestamp = self._fetch_rsa_params()
        encrypted_password = self._encrypt_password(rsa_key)
        client_id, request_id = self._request_auth(encrypted_password,
                                                   rsa_timestamp)
        self._send_steam_guard_code(client_id)
        refresh_token = self._request_refresh_token(client_id, request_id)
        finalize_response = self._finalize_login(refresh_token)
        self._send_transfer_info(finalize_response)
        return self.steam_id

    def _fetch_rsa_params(self) -> tuple[rsa.PublicKey, str]:
        url = IAuthenticationServiceEndpoint.GetPasswordRSAPublicKey
        params = {'account_name': self.username}
        key_response = self.session.get(url, params=params, headers=self.headers).json()
        rsa_mod = int(key_response.get('response').get('publickey_mod'), 16)
        rsa_exp = int(key_response.get('response').get('publickey_exp'), 16)
        rsa_timestamp = key_response.get('response').get('timestamp')
        return rsa.PublicKey(rsa_mod, rsa_exp), rsa_timestamp

    def _encrypt_password(self, rsa_key: rsa.PublicKey) -> bytes:
        encoded_password = self.password.encode('utf-8')
        encrypted_rsa = rsa.encrypt(encoded_password, rsa_key)
        return base64.b64encode(encrypted_rsa)

    def _request_auth(self, encrypted_password: bytes, rsa_timestamp: str)\
            -> tuple[str, str]:
        url = IAuthenticationServiceEndpoint.BeginAuthSessionViaCredentials
        request_auth_data = {
            'persistence': '1',
            'encrypted_password': encrypted_password,
            'account_name': self.username,
            'encryption_timestamp': rsa_timestamp
        }
        request_auth_response = self.session.post(url, headers=self.headers, data=request_auth_data).json()
        client_id = request_auth_response.get('response').get('client_id')
        self.steam_id = request_auth_response.get('response').get('steamid')
        request_id = request_auth_response.get('response').get('request_id')
        return client_id, request_id

    def _send_steam_guard_code(self, client_id: str) -> None:
        url =\
            IAuthenticationServiceEndpoint.UpdateAuthSessionWithSteamGuardCode
        update_data = {
            'client_id': client_id,
            'steamid': self.steam_id,
            'code_type': 3,
            'code': generate_one_time_code(self.shared_secret)
        }
        self.session.post(url, headers=self.headers, data=update_data)

    def _request_refresh_token(self, client_id: str, request_id: str) -> str:
        url = IAuthenticationServiceEndpoint.PollAuthSessionStatus
        pool_data = {
            'client_id': client_id,
            'request_id': request_id,
        }
        poll_response = self.session.post(url, headers=self.headers, data=pool_data).json()
        refresh_token = poll_response.get('response').get('refresh_token')
        return refresh_token

    def _finalize_login(self, refresh_token: str) -> dict:
        redir_url = Urls.COMMUNITY + '/login/home/?goto='
        finalize_url = Urls.LOGIN + '/jwt/finalizelogin'
        finalize_data = {
            'nonce': refresh_token,
            'sessionid': self.session.cookies.get('sessionid'),
            'redir': redir_url
        }
        headers = {
            'Referer': redir_url,
            'Origin': 'https://steamcommunity.com'
        }
        headers.update(self.headers)
        finalize_response = self.session.post(finalize_url, headers=headers, data=finalize_data).json()
        return finalize_response

    def _send_transfer_info(self, finalize_response: dict) -> None:
        parameters = finalize_response.get('transfer_info')
        for pass_data in parameters:
            pass_data['params']['steamID'] = finalize_response.get('steamID')
            self.session.post(pass_data.get('url'), headers=self.headers, data=pass_data.get('params'))
