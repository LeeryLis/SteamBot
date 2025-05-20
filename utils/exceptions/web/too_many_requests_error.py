class TooManyRequestsError(Exception):
    """Исключение для ошибок 429 (Too Many Requests)"""
    def __init__(self, message="Серверу нужно передохнуть, будь человеком"):
        self.message = message
        super().__init__(self.message)
