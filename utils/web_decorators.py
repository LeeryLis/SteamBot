from functools import wraps
import requests


def handle_status_codes_using_attempts(max_attempts: int = 4, status_codes: list[int] = None):
    if not status_codes:
        status_codes = [500, 502]  # Дефолтные значения

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            response: requests.Response = func(*args, **kwargs)
            for attempt in range(max_attempts):
                if not response or response.status_code in status_codes:
                    response: requests.Response = func(*args, **kwargs)
                    continue
                break
            return response

        return wrapper

    return decorator
