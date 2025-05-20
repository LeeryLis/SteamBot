from abc import ABC, abstractmethod

from tools.rate_limiter import RateLimiter


class BasicRateLimit(ABC):
    def __init__(self):
        self.rate_limiter = RateLimiter()
        self.set_service_limits()

    @abstractmethod
    def set_service_limits(self):
        pass
