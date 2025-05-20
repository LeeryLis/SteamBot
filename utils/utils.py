import re

def is_str_number(s: str) -> bool:
    pattern = r'^-?\d+(\.\d+)?$'
    return bool(re.match(pattern, s))

def is_str_int(s: str) -> bool:
    pattern = r'^-?\d+$'
    return bool(re.match(pattern, s))

def text_between(text: str, begin: str, end: str) -> str:
    start = text.index(begin) + len(begin)
    end = text.index(end, start)
    return text[start:end]