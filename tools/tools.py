from rich.text import Text


def escape_brackets(text: str) -> str:
    return text.replace("[", "\[")

def rich_auto_text(obj) -> Text:
    return Text(str(obj), style="repr.number" if isinstance(obj, (int, float)) else "")
