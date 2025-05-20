from functools import wraps

from .rate_limiter import RateLimiter


def rate_limited(service_name: str, rate_limiter: RateLimiter):
    """
    Декоратор для управления задержкой между вызовами метода, обращающегося к сервису.
    :param service_name: Название сервиса, для которого применяется ограничение.
    :param rate_limiter: Экземпляр RateLimiter для управления задержками.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            rate_limiter.wait_for_service(service_name)
            return func(*args, **kwargs)
        return wrapper
    return decorator

def rate_limited_cls(service_name: str):
    """
    Декоратор для управления задержкой между вызовами метода, обращающегося к сервису.
    Адаптирован для использования в классах (где используется self.rate_limiter, который нельзя передать в декоратор)
    :param service_name: Название сервиса, для которого применяется ограничение.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self.rate_limiter.wait_for_service(service_name)
            return func(self, *args, **kwargs)
        return wrapper
    return decorator
