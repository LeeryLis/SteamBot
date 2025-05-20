import time


class ServiceLimit:
    def __init__(self, min_delay: float):
        """
        :param min_delay: Минимальная задержка между запросами (в секундах).
        """
        self.min_delay = min_delay
        self.last_request_time = 0

    def update_last_request_time(self):
        self.last_request_time = time.time()

    def set_min_delay(self, min_delay: float):
        self.min_delay = min_delay

    def time_since_last_request(self) -> float:
        return time.time() - self.last_request_time
