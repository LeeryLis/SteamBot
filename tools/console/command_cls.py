from inspect import Parameter, signature
from typing import get_origin, get_args, Collection, Any, Callable
from rich.console import Console

from tools import escape_brackets


class Command:
    def __init__(
            self, *,
            action: Callable, aliases: list, description: str, usage: str,
            flag_aliases: dict = None, flag_descriptions: dict = None
    ):
        self.action = action
        self.aliases = aliases
        self.description = description
        self.usage = usage
        self.flag_aliases = flag_aliases
        self.flag_descriptions = flag_descriptions

    def execute(self, *args):
        try:
            if args:
                positional, kwargs = self._parse_args(args)
                self.action(*positional, **kwargs)
            else:
                self.action()
        except TypeError:
            Console().print(f"Usage: [green]{escape_brackets(self.usage)}[/green]")
        except Exception as ex:
            Console().print(f"[red]{ex}[/red]\nUsage: [green]{escape_brackets(self.usage)}[/green]")

    @staticmethod
    def _is_flag(s: str) -> bool:
        return s.startswith("-") and not (len(s) > 1 and s[1].isdigit())

    def _convert(self, raw_value, annotation):
        if annotation == Parameter.empty:
            return raw_value

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin in (list, tuple, set):
            items = raw_value if isinstance(raw_value, list) else [raw_value]
            subtype = args[0] if args else str
            converted = [self._convert(item, subtype) for item in items]
            return origin(converted)

        if annotation is dict:
            key_type, val_type = args if args else (str, str)
            items = raw_value if isinstance(raw_value, list) else [s.strip() for s in raw_value.split(",") if s.strip()]
            result = {}
            for item in items:
                if "=" not in item:
                    raise ValueError(f"Dict argument must be key=value, got '{item}'")
                k, v = item.split("=", 1)
                result[self._convert(k, key_type)] = self._convert(v, val_type)
            return result

        if annotation is bool:
            if isinstance(raw_value, str):
                return raw_value.lower() in ("1", "true", "yes", "on")
            return bool(raw_value)

        try:
            return annotation(raw_value)
        except Exception:
            raise ValueError(f"Cannot convert '{raw_value}' to {annotation}")

    def _parse_list_param(self, i: int, args_list, subtype) -> (Collection[Any], int):
        collected = []
        while i < len(args_list):
            raw = args_list[i]
            if self._is_flag(raw):
                break
            try:
                val = subtype(raw)
            except ValueError:
                break
            collected.append(val)
            i += 1
        return collected, i

    def _parse_args(self, args_list):
        sig = signature(self.action)
        params = list(sig.parameters.values())
        positional = []
        kwargs = {}

        i = 0
        j = 0
        while j < len(params):
            param = params[j]
            if i >= len(args_list):
                break

            origin = get_origin(param.annotation)
            args_type = get_args(param.annotation)

            if self._is_flag(args_list[i]):
                name = self.flag_aliases.get(args_list[i], args_list[i].lstrip("-"))
                flag_param = next((p for p in params if p.name == name), None)
                if not flag_param:
                    raise ValueError(f"Unknown flag: {args_list[i]}")

                if flag_param.annotation is bool:
                    kwargs[name] = True
                    i += 1
                else:
                    if i + 1 >= len(args_list):
                        raise ValueError(f"Flag {args_list[i]} requires a value")
                    kwargs[name] = self._convert(args_list[i + 1], flag_param.annotation)
                    i += 2
            elif origin in (list, tuple, set):
                subtype = args_type[0] if args_type else str
                collected, i = self._parse_list_param(i, args_list, subtype)
                positional.append(self._convert(collected, param.annotation))
                j += 1
            elif param.annotation is dict:
                positional.append(self._convert(args_list[i], param.annotation))
                i += 1
                j += 1
            else:
                if i < len(args_list):
                    positional.append(self._convert(args_list[i], param.annotation))
                    i += 1
                    j += 1
                elif param.default != Parameter.empty:
                    positional.append(param.default)
                else:
                    raise ValueError(f"Missing argument: {param.name}")

        return positional, kwargs
