import re

def is_str_int(s: str) -> bool:
    pattern = r'^-?\d+$'
    return bool(re.match(pattern, s))
