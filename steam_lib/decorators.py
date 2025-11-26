import os
import inspect
from functools import wraps

import requests

from .login_selenium import LoginExecutorSelenium


_cached_login_executor = None

def _get_cached_executor():
    global _cached_login_executor
    if _cached_login_executor is not None:
        return _cached_login_executor

    exec_obj = LoginExecutorSelenium(
            os.getenv('USER_NAME'),
            os.getenv('PASSWORD'),
            os.getenv('SHARED_SECRET')
        )
    _cached_login_executor = exec_obj
    return _cached_login_executor

def _get_session_from_args(fn, args, kwargs):
    if "session" in kwargs and isinstance(kwargs["session"], requests.Session):
        return kwargs["session"]

    sig = inspect.signature(fn)
    params = list(sig.parameters.keys())
    if "session" in params:
        idx = params.index("session")
        if idx < len(args) and isinstance(args[idx], requests.Session):
            return args[idx]

    if len(args) >= 1:
        self_obj = args[0]
        session = getattr(self_obj, "session", None)
        if isinstance(session, requests.Session):
            return session
    return None

def refresh_cookies():
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            session = _get_session_from_args(fn, args, kwargs)
            if session is None:
                raise RuntimeError("Не найден аргумент session у функции '{}'".format(fn.__name__))

            login_executor = _get_cached_executor()
            login_executor.session = session
            login_executor.login_or_refresh_cookies()

            return fn(*args, **kwargs)
        return wrapper
    return decorator
