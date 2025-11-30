class TooManyRequestsError(Exception):
    """Исключение для ошибок 429 (Too Many Requests)"""
    def __init__(self, message="Слишком много обращений к серверу"):
        self.message = message
        super().__init__(self.message)
