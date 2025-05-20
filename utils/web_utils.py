def api_request():
    pass

def handle_429_status_code(func: callable, *args, **kwargs) -> bool:
    from rich.console import Console
    from datetime import datetime
    from utils.exceptions import TooManyRequestsError

    try:
        func(*args, **kwargs)
        return False
    except TooManyRequestsError as ex:
        Console().print(
            f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} "
            f"Ошибка: {ex}"
        )
        return True
