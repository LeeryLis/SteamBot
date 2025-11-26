import subprocess
import time
from datetime import datetime, timedelta, timezone

import requests
import pickle
import os
import json

from requests.cookies import RequestsCookieJar
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

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

        self.urls = {
            Urls.STORE: [Urls.ACCOUNT, Urls.STORE + "/login"],
            Urls.COMMUNITY: [Urls.MY_INVENTORY, Urls.COMMUNITY + "/login/home/?goto=login"]
        }

        self.first_login_time_file = f"{project_root}/data/saved_session/first_login.json"
        self.cookies_file = f"{project_root}/data/saved_session/cookies.pkl"
        self.steam_id_file = f"{project_root}/data/saved_session/steam_id.txt"
        self.selenium_profile_dir = f"{project_root}/data/saved_session/selenium_profile"

    def login_or_refresh_cookies(self, cookie_max_age: timedelta = timedelta(hours=24)) -> None:
        steam_login_refresh_time = self.session.cookies.get("steamDidLoginRefresh", domain=".steamcommunity.com")
        if steam_login_refresh_time is None:
            self._load_cookies_from_file()

        if steam_login_refresh_time is None:
            steam_login_refresh_time = self._load_first_login_time()

        if steam_login_refresh_time is not None:
            try:
                timestamp = int(steam_login_refresh_time)
                last_refresh = datetime.fromtimestamp(timestamp, timezone.utc)
                if datetime.now(timezone.utc) - last_refresh < cookie_max_age:
                    return
                print("Refresh cookies...")
            except ValueError:
                pass

        manually = (self.shared_secret == "" and not steam_login_refresh_time)
        self._selenium_login(manually)
        self._save_cookies_to_file()

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
        with open(self.cookies_file, 'wb') as f:
            pickle.dump(self.session.cookies, f)
        return True

    def _load_cookies_from_file(self) -> bool:
        try:
            with open(self.cookies_file, 'rb') as f:
                self.session.cookies.update(pickle.load(f))
        except FileNotFoundError:
            return False
        return True

    def _load_cookies_into_selenium_driver(self, driver) -> bool:
        try:
            with open(self.cookies_file, "rb") as f:
                cookies = pickle.load(f)

            for domain in self.urls.keys():
                driver.get(domain)
                for c in cookies:
                    if domain.endswith(c.domain):
                        cookie_dict = {
                            "name": c.name,
                            "value": c.value,
                            "domain": c.domain,
                            "path": c.path,
                            "secure": c.secure,
                        }
                        if c.expires:
                            cookie_dict["expiry"] = c.expires
                        try:
                            driver.add_cookie(cookie_dict)
                        except Exception as e:
                            print(f"Не удалось добавить куку {c.name}: {e}")
                driver.refresh()
                # Для полного обновления (особенно sessionid)
                self._get_selenium_cookies_into_requests_session(driver)
            return True
        except FileNotFoundError:
            return False

    def _get_selenium_cookies_into_requests_session(self, driver) -> None:
        for domain in self.urls.keys():
            driver.get(domain)
            jar = RequestsCookieJar()
            for cookie in driver.get_cookies():
                jar.set(
                    name=cookie['name'],
                    value=cookie['value'],
                    domain=cookie['domain'],
                    path=cookie.get('path', '/'),
                    secure=cookie.get('secure', False),
                    rest={'HttpOnly': cookie.get('httpOnly', False)}
                )
            self.session.cookies.update(jar)

    def _fill_login_form(self, driver, url: str, manually: bool = False) -> None:
        driver.get(url)

        if not manually:
            username_input = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((
                    By.XPATH,
                    "//div[(contains(text(), 'Sign in') or contains(text(), 'Войдите'))]/following-sibling::input[@type='text']"
                ))
            )
            username_input.send_keys(self.username)

            password_input = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, "input[type='password']"))
            )
            password_input.send_keys(self.password)

            login_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@data-featuretarget="login"]//button[@type="submit"]'))
            )
            login_button.click()

            code_inputs = WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "input._3xcXqLVteTNHmk-gh9W65d.Focusable"))
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

        self._get_selenium_cookies_into_requests_session(driver)

    def _save_first_login_time(self) -> None:
        if os.path.exists(self.first_login_time_file):
            return

        first_login_time = int(datetime.now(timezone.utc).timestamp())
        with open(self.first_login_time_file, "w", encoding="utf-8") as f:
            json.dump({"first_login_time": first_login_time}, f)

    def _load_first_login_time(self) -> str | None:
        if not os.path.exists(self.first_login_time_file):
            return None

        with open(self.first_login_time_file, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return data.get("first_login_time")
            except (json.JSONDecodeError, ValueError):
                return None

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

        driver = webdriver.Chrome(service=service, options=options)
        self._load_cookies_into_selenium_driver(driver)

        try:
            for domain, (url_check, url_login) in self.urls.items():
                is_logged, err = self._is_logged(url_check)
                if err:
                    print("Error: login check failed")
                if not is_logged:
                    self._fill_login_form(driver, url_login, manually)
                    self._save_first_login_time()

        finally:
            driver.quit()
