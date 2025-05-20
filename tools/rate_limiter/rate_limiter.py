import time
from .service_limit import ServiceLimit


class RateLimiter:
    def __init__(self):
        # Словарь лимитов, где ключ — имя сервиса, а значение — экземпляр ServiceLimit
        """
            Лучше, конечно, использовать enum, но зачем такие сложности?
            Будет проект расширяться, появится необходимость, можно накрутить.
            Тем более enum должен формироваться на стороне кода-пользователя и им же поддерживаться
        """
        self.limits: dict[str, ServiceLimit] = {}

    def set_limit(self, service: str, min_delay: float):
        """
        Устанавливает или обновляет лимит для сервиса.
        :param service: Имя сервиса (например, URL или идентификатор API).
        :param min_delay: Минимальное время задержки в секундах.
        """
        if service in self.limits:
            self.limits[service].set_min_delay(min_delay)
        else:
            self.limits[service] = ServiceLimit(min_delay)

    def wait_for_service(self, service: str):
        """
        Выполняет ожидание, если с последнего запроса прошло меньше min_delay.
        :param service: Имя сервиса.
        """
        if service not in self.limits:
            raise ValueError(f"No limit set for service '{service}'")

        service_limit = self.limits[service]
        elapsed_time = service_limit.time_since_last_request()

        if elapsed_time < service_limit.min_delay:
            wait_time = service_limit.min_delay - elapsed_time
            time.sleep(wait_time)

        service_limit.update_last_request_time()
