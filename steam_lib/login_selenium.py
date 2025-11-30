import subprocess
import time
from typing import Any, Optional

import requests
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

from .guard import generate_one_time_code
from enums import Urls


class LoginExecutorSelenium:
    def __init__(self, username: str, password: str, shared_secret: str,
                 selenium_profile_dir: str):
        self.username = username
        self.password = password
        self.shared_secret = shared_secret
        self.selenium_profile_dir = selenium_profile_dir

        self.login_urls = {
            Urls.STORE: [Urls.ACCOUNT, Urls.STORE + "/login"],
            Urls.COMMUNITY: [Urls.MY_INVENTORY, Urls.COMMUNITY + "/login/home/?goto=login"]
        }

    def perform_selenium_login_and_extract(
            self, session: requests.Session, prior_urls: dict[str, str], manually: bool = False
    ) -> dict[str, tuple[Optional[str], Optional[int]]]:
        options = Options()
        if not manually:
            options.add_argument("--headless=new")
        options.add_argument(f"--user-data-dir={self.selenium_profile_dir}")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--window-size=1200,800")
        options.add_argument("--log-level=3")
        options.add_argument("--disable-logging")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-infobars")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-features=SameSiteByDefaultCookies,BlockThirdPartyCookies")
        options.add_argument("--enable-features=NetworkService,NetworkServiceInProcess")

        service = Service(log_output=os.devnull)
        try:
            service.creation_flags = subprocess.CREATE_NO_WINDOW
        except Exception:
            pass

        priors: dict[str, tuple[Optional[str], Optional[int]]] = {}

        with webdriver.Chrome(service=service, options=options) as driver:
            self._get_selenium_cookies_into_requests_session(driver, session)

            try:
                for domain, (url_check, url_login) in self.login_urls.items():
                    is_logged, err = self._is_logged(session, url_check)
                    if err:
                        print("Error: login check failed for", domain)
                    if not is_logged:
                        self._fill_login_form(driver, url_login, manually)
                        self._get_selenium_cookies_into_requests_session(driver, session)

                for origin, referer in prior_urls.items():
                    try:
                        driver.get(referer)
                        token = driver.execute_script("return window.g_wapit || null;")
                        expiry = self._parse_jwt_exp(token)
                        priors[origin] = (token, expiry)
                    except Exception as ex:
                        print(f"Failed to read prior for {origin}: {ex}")
                        priors[origin] = (None, None)

                self._get_selenium_cookies_into_requests_session(driver, session)
            except Exception as ex:
                print(f"Error while using webdriver: {ex}")

        return priors

    @staticmethod
    def _get_selenium_cookies_into_requests_session(driver, session: requests.Session) -> None:
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

        session.cookies.update(jar)

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

    @staticmethod
    def _is_logged(session: requests.Session, url, attempts_count: int = 3) -> (bool, bool):
        for attempt in range(attempts_count):
            try:
                response = session.get(url, allow_redirects=False)
                return not (
                    response.status_code in (301, 302)
                    and "login" in response.headers.get("Location", "").lower()
                ), False
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ReadTimeout,
                    requests.exceptions.RequestException):
                time.sleep(1)
        return False, True
