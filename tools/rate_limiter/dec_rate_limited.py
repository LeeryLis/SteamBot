import time
from functools import wraps

from .service_limit import ServiceLimit


def rate_limited(min_delay: float):
    """
        Декоратор для управления задержкой между вызовами метода, обращающегося к сервису.
    """
    service_limit = ServiceLimit(min_delay)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            elapsed_time = service_limit.time_since_last_request()

            if elapsed_time < service_limit.min_delay:
                wait_time = service_limit.min_delay - elapsed_time
                time.sleep(wait_time)

            service_limit.update_last_request_time()
            return func(*args, **kwargs)
        return wrapper
    return decorator
