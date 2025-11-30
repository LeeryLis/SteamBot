import datetime
import time
from typing import Optional

import requests
import json
import base64

from tools.file_store import FileStore, FileStoreType
from steam_lib import LoginExecutorSelenium
from utils.web_utils import api_request
from enums import Urls
from _root import project_root


class SessionManager:
    def __init__(self, username: str, password: str, shared_secret: str,
                 session: Optional[requests.Session] = None):
        self.username = username
        self.password = password
        self.shared_secret = shared_secret

        self.session = session

        self.priors: dict[str, tuple[Optional[str], Optional[int]]] = {}

        self.prior_urls = {
            Urls.COMMUNITY: Urls.MY_INVENTORY,
            Urls.STORE: Urls.ACCOUNT
        }
        self.cookies_urls = [Urls.STORE, Urls.COMMUNITY]

        self.prior_file = f"{project_root}/data/saved_session/prior.pkl"
        self.cookies_file = f"{project_root}/data/saved_session/cookies.pkl"
        self.selenium_profile_dir = f"{project_root}/data/saved_session/selenium_profile"

        self._cookies_already_loaded = False
        self.cookies_hash = None

        self._selenium_executor = LoginExecutorSelenium(
            username=self.username,
            password=self.password,
            shared_secret=self.shared_secret,
            selenium_profile_dir=self.selenium_profile_dir
        )

    def ensure_session(self) -> None:
        if not self._cookies_already_loaded:
            self._load_cookies_from_file()
            self._cookies_already_loaded = True

        if not self.priors:
            if not self._load_prior_from_file():
                self._perform_selenium_login_and_store_priors()
                return

        for origin, referer in self.prior_urls.items():
            _, expiry = self.priors.get(origin, (None, None))
            if self._is_time_to_refresh(expiry):
                self._refresh_cookies(origin, referer)

    def maybe_save_update_cookies(self) -> None:
        new_hash = self._calc_cookie_hash()
        if new_hash != self.cookies_hash:
            self._save_cookies_to_file()
            self.cookies_hash = new_hash

    def _calc_cookie_hash(self) -> int:
        data = tuple(sorted((c.name, c.value) for c in self.session.cookies))
        return hash(data)

    @staticmethod
    def _parse_jwt_exp(jwt_token: Optional[str]) -> Optional[int]:
        try:
            if not jwt_token:
                return None
            payload_b64 = jwt_token.split('.')[1]
            padded = payload_b64 + '=' * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode())
            return int(payload.get('exp')) if 'exp' in payload else None
        except Exception:
            return None

    def _do_steam_jwt_refresh(self, origin: str, referer: str):
        data = {
            "redir": referer
        }
        headers = {
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
            "Origin": origin
        }
        response_1 = api_request(
            self.session,
            "POST",
            f"{Urls.LOGIN}/jwt/ajaxrefresh",
            headers=headers,
            data=data
        )
        if response_1.status_code != 200:
            raise RuntimeError(f"ajaxrefresh failed: {response_1.status_code}")

        try:
            obj = response_1.json()
        except ValueError:
            raise RuntimeError("ajaxrefresh returned non-json")

        if not obj.get("success"):
            raise RuntimeError("ajaxrefresh returned success=false")

        login_url = obj.get("login_url")
        if not login_url:
            raise RuntimeError("ajaxrefresh did not provide login_url")

        payload = dict(obj)
        prior_token, _ = self.priors.get(origin, (None, None))
        if prior_token:
            payload['prior'] = prior_token

        response_2 = api_request(
            self.session,
            "POST",
            login_url,
            headers=headers,
            data=payload
        )
        if response_2.status_code != 200:
            raise RuntimeError(f"second refresh post failed: {response_2.status_code}")

        try:
            response_2_json = response_2.json()
        except ValueError:
            raise RuntimeError("second refresh returned non-json")

        if response_2_json.get("result") == 1 and response_2_json.get("token"):
            new_token = response_2_json['token']
            rt_expiry = response_2_json.get('rtExpiry')
            return {"token": new_token, "rtExpiry": rt_expiry, "response": response_2_json}
        else:
            raise RuntimeError("refresh failed or returned no token")

    def _refresh_cookies(self, origin, referer) -> None:
        try:
            result = self._do_steam_jwt_refresh(origin=origin, referer=referer)
            new_token = result["token"]
            rt_expiry = result.get("rtExpiry")
            if not rt_expiry:
                rt_expiry = self._parse_jwt_exp(new_token)

            self.priors[origin] = (new_token, rt_expiry)
            self._save_prior_to_file()
        except Exception as e:
            print("refresh failed:", e)

    def _perform_selenium_login_and_store_priors(self) -> None:
        priors = self._selenium_executor.perform_selenium_login_and_extract(
            session=self.session,
            prior_urls=self.prior_urls,
            manually=self.shared_secret == ""
        )
        self.priors.update(priors)
        self._save_prior_to_file()
        self._save_cookies_to_file()

    @staticmethod
    def _is_time_to_refresh(
            expiry: Optional[int],
            refresh_threshold: datetime.timedelta = datetime.timedelta(minutes=30)
    ) -> bool:
        if expiry is None:
            return True
        now = int(time.time())
        return now >= expiry - refresh_threshold.total_seconds()

    def _save_cookies_to_file(self) -> bool:
        file_store = FileStore.from_type(FileStoreType.PICKLE)
        return file_store.save(self.cookies_file, self.session.cookies)

    def _load_cookies_from_file(self) -> bool:
        file_store = FileStore.from_type(FileStoreType.PICKLE)
        loaded_cookies = file_store.load(self.cookies_file, default=None)

        if loaded_cookies is None:
            return False

        self.session.cookies.update(loaded_cookies)
        self.cookies_hash = self._calc_cookie_hash()
        return True

    def _save_prior_to_file(self) -> bool:
        file_store = FileStore.from_type(FileStoreType.PICKLE)
        return file_store.save(self.prior_file, self.priors)

    def _load_prior_from_file(self) -> bool:
        file_store = FileStore.from_type(FileStoreType.PICKLE)
        loaded_prior = file_store.load(self.prior_file, default=None)

        if loaded_prior is None:
            return False

        self.priors = loaded_prior
        return True
