import subprocess
import time
from typing import Any

import requests
import pickle
import os
import json
import base64

from requests.cookies import RequestsCookieJar
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions

from utils.web_utils import api_request
from .guard import generate_one_time_code
from enums import Urls
from _root import project_root


class LoginExecutorSelenium:
    def __init__(self, username: str, password: str, shared_secret: str,
                 session: requests.Session = None) -> None:
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.session = session

        self.prior_token = None
        self.prior_expiry = None

        self.urls = {
            Urls.STORE: [Urls.ACCOUNT, Urls.STORE + "/login"],
            Urls.COMMUNITY: [Urls.MY_INVENTORY, Urls.COMMUNITY + "/login/home/?goto=login"]
        }
        self.cookies_urls = [
            Urls.STORE, Urls.COMMUNITY
        ]

        self.prior_file = f"{project_root}/data/saved_session/prior.pkl"
        self.cookies_file = f"{project_root}/data/saved_session/cookies.pkl"
        self.selenium_profile_dir = f"{project_root}/data/saved_session/selenium_profile"

    def login_or_refresh_cookies(self) -> None:
        self._load_cookies_from_file()
        if self.prior_token is not None or self._load_prior_from_file():
            if self._is_time_to_refresh():
                self._refresh_cookies()
        else:
            self._login()

    @staticmethod
    def _parse_jwt_exp(jwt_token) -> int | None:
        try:
            payload_b64 = jwt_token.split('.')[1]
            padded = payload_b64 + '=' * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(padded).decode())
            return int(payload.get('exp')) if 'exp' in payload else None
        except Exception:
            return None

    def _do_steam_jwt_refresh(self, session: requests.Session, referer: str):
        data = {
            "redir": referer
        }
        headers = {
            "Referer": referer,
            "X-Requested-With": "XMLHttpRequest",
            "Origin": Urls.COMMUNITY
        }
        response_1 = api_request(
            session,
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
        if self.prior_token:
            payload['prior'] = self.prior_token

        response_2 = api_request(
            session,
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

    def _refresh_cookies(self) -> None:
        try:
            result = self._do_steam_jwt_refresh(self.session, referer=Urls.MY_INVENTORY)
            new_token = result["token"]
            rt_expiry = result.get("rtExpiry")
            if not rt_expiry:
                rt_expiry = self._parse_jwt_exp(new_token)

            self.prior_token = new_token
            self.prior_expiry = rt_expiry
            self._save_prior_to_file(self.prior_token, self.prior_expiry)
        except Exception as e:
            print("refresh failed:", e)

    def _login(self) -> None:
        manually = (self.shared_secret == "")
        self._selenium_login(manually)
        self._save_cookies_to_file()

    def _is_time_to_refresh(self, refresh_threshold: int = 1800) -> bool:
        if self.prior_expiry is None:
            return True

        now = int(time.time())
        if now >= self.prior_expiry - refresh_threshold:
            return True

        return False

    def _is_logged(self, url, attempts_count: int = 3) -> (bool, bool):
        for attempt in range(attempts_count):
            try:
                response = self.session.get(url, allow_redirects=False)
                return not (
                        response.status_code in (301, 302)
                        and "login" in response.headers.get("Location", "").lower()
                ), False
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.RequestException):
                time.sleep(1)
        return False, True

    def _save_cookies_to_file(self) -> bool:
        dir_path = os.path.dirname(self.cookies_file)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        try:
            with open(self.cookies_file, 'wb') as f:
                pickle.dump(self.session.cookies, f)
            return True
        except Exception as e:
            print("Failed to save cookies:", e)
            return False

    def _load_cookies_from_file(self) -> bool:
        try:
            with open(self.cookies_file, 'rb') as f:
                self.session.cookies.update(pickle.load(f))
        except FileNotFoundError:
            return False
        return True

    def _get_selenium_cookies_into_requests_session(self, driver) -> None:
        all_cookies_resp: dict[str, Any] = driver.execute_cdp_cmd("Network.getAllCookies", {})
        cookies = all_cookies_resp.get("cookies", [])

        jar = RequestsCookieJar()
        for c in cookies:
            name = c.get("name")
            value = c.get("value")
            domain = c.get("domain")
            path = c.get("path", "/")
            secure = bool(c.get("secure", False))
            http_only = bool(c.get("httpOnly", False))
            expires = c.get("expires", None)
            same_site = c.get("sameSite", None)
            rest = {}
            if http_only:
                rest['HttpOnly'] = True
            if same_site is not None:
                rest['SameSite'] = same_site
            if 'priority' in c:
                rest['Priority'] = c.get('priority')

            jar.set(
                name=name,
                value=value,
                domain=domain,
                path=path,
                secure=secure,
                expires=expires if expires not in (0, -1) else None,
                rest=rest
            )

        self.session.cookies.update(jar)

    def _fill_login_form(self, driver, url: str, manually: bool = False) -> None:
        driver.get(url)

        if not manually:
            username_input = WebDriverWait(driver, 10).until(
                expected_conditions.visibility_of_element_located((
                    By.XPATH,
                    "//div[(contains(text(), 'Sign in') or contains(text(), 'Войдите'))]"
                    "/following-sibling::input[@type='text']"
                ))
            )
            username_input.send_keys(self.username)

            password_input = WebDriverWait(driver, 10).until(
                expected_conditions.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
            )
            password_input.send_keys(self.password)

            login_button = WebDriverWait(driver, 10).until(
                expected_conditions.element_to_be_clickable((
                    By.XPATH, '//div[@data-featuretarget="login"]//button[@type="submit"]'))
            )
            login_button.click()

            code_inputs = WebDriverWait(driver, 20).until(
                expected_conditions.presence_of_all_elements_located((
                    By.CSS_SELECTOR, "input._3xcXqLVteTNHmk-gh9W65d.Focusable"))
            )
            time.sleep(0.5)
            code = generate_one_time_code(self.shared_secret)
            for i, char in enumerate(code):
                time.sleep(0.3)
                code_inputs[i].send_keys(char)

            WebDriverWait(driver, 10).until(
                lambda d: any(c['name'] == 'steamLoginSecure' for c in d.get_cookies())
            )
        else:
            print("Пожалуйста, войдите вручную в открывшемся окне браузера...")
            WebDriverWait(driver, 300).until(
                lambda d: any(c['name'] == 'steamLoginSecure' for c in d.get_cookies())
            )

    def _get_prior(self, driver):
        driver.get(Urls.MY_INVENTORY)
        self.prior_token = driver.execute_script("return window.g_wapit || null;")
        self.prior_expiry = self._parse_jwt_exp(self.prior_token)
        return self.prior_token, self.prior_expiry

    def _save_prior_to_file(self, prior_token, prior_expiry) -> bool:
        dir_path = os.path.dirname(self.prior_file)
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
        try:
            with open(self.prior_file, 'wb') as f:
                pickle.dump((prior_token, prior_expiry), f)
            return True
        except Exception as e:
            print("Failed to save prior:", e)
            return False

    def _load_prior_from_file(self) -> bool:
        if not os.path.exists(self.prior_file):
            return False
        try:
            with open(self.prior_file, 'rb') as f:
                prior_token, prior_expiry = pickle.load(f)
            self.prior_token = prior_token
            self.prior_expiry = prior_expiry
            return True
        except Exception as e:
            print("Failed to load prior:", e)
            return False

    def _selenium_login(self, manually: bool = False) -> None:
        options = Options()
        if not manually:
            options.add_argument("--headless=new")  # headless режим
        options.add_argument(f"--user-data-dir={self.selenium_profile_dir}")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--window-size=1200,800")
        options.add_argument("--log-level=3")  # скрыть INFO и WARNING
        options.add_argument("--disable-logging")
        options.add_argument("--no-sandbox")  # отключить sandbox
        options.add_argument("--disable-dev-shm-usage")  # для контейнеров / ограниченной памяти
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-features=SameSiteByDefaultCookies,BlockThirdPartyCookies")
        options.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")

        service = Service(log_output=os.devnull)
        service.creation_flags = subprocess.CREATE_NO_WINDOW

        with webdriver.Chrome(service=service, options=options) as driver:
            self._get_selenium_cookies_into_requests_session(driver)

            try:
                for domain, (url_check, url_login) in self.urls.items():
                    is_logged, err = self._is_logged(url_check)
                    if err:
                        print("Error: login check failed")
                    if not is_logged:
                        self._fill_login_form(driver, url_login, manually)
                        self._get_selenium_cookies_into_requests_session(driver)
                self.prior_token, self.prior_expiry = self._get_prior(driver)
                self._save_prior_to_file(self.prior_token, self.prior_expiry)
            except Exception as ex:
                print(f"Error while using webdriver: {ex}")
