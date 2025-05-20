import inspect
from typing import Callable, Any, Sequence
from tools.console.param_type import ParamType
from rich.text import Text
from rich.console import Console


class Param:
    def __init__(
            self,
            *,
            action: Callable[..., Any],
            description: str,
            param_type: ParamType,
            usage: str = '',
            arg_number: int = 0
    ):
        self.action = action
        self.description = description
        self.usage = usage
        self.param_type = param_type
        self.arg_number = arg_number

    def _get_argspec(self) -> tuple[inspect.FullArgSpec, list[str]]:
        argspec = inspect.getfullargspec(self.action)
        if not argspec.args:
            return argspec, []
        argspec_args = argspec.args[1:] if argspec.args[0] == 'self' else argspec.args
        return argspec, argspec_args

    @staticmethod
    def _convert_positional_args(
            args: Sequence[str], argspec: inspect.FullArgSpec, argspec_args: list[str]
    ) -> tuple[list[Any], int]:
        converted_args = []
        args_index = 0
        for arg_name in argspec_args:
            if args_index < len(args):
                arg = args[args_index]
                annotation = argspec.annotations.get(arg_name, None)
                if annotation:
                    converted_arg = annotation(arg)
                else:
                    converted_arg = arg
                converted_args.append(converted_arg)
                args_index += 1
            else:
                if argspec.defaults and arg_name in argspec.args[-len(argspec.defaults):]:
                    default_index = argspec.args.index(arg_name) - len(argspec.args) + len(argspec.defaults)
                    converted_args.append(argspec.defaults[default_index])
                else:
                    raise TypeError(f"Не передан обязательный аргумент {arg_name}")
        return converted_args, args_index

    @staticmethod
    def _convert_varargs(args: Sequence[str], argspec: inspect.FullArgSpec, args_index: int) -> list[Any]:
        if argspec.varargs:
            varargs_name = argspec.varargs
            varargs_annotation = argspec.annotations.get(varargs_name, None)
            if varargs_annotation and varargs_annotation != Any:
                converted_varargs = [varargs_annotation(arg) for arg in args[args_index:]]
            else:
                converted_varargs = args[args_index:]
            return converted_varargs
        else:
            return []

    @staticmethod
    def _convert_kwonlyargs(args: Sequence[str], argspec: inspect.FullArgSpec, args_index: int) -> list[Any]:
        if argspec.kwonlyargs:
            converted_args = []
            for arg_name in argspec.kwonlyargs:
                if args_index < len(args):
                    arg = args[args_index]
                    annotation = argspec.annotations.get(arg_name, None)
                    if annotation:
                        converted_arg = annotation(arg)
                    else:
                        converted_arg = arg
                    converted_args.append(converted_arg)
                    args_index += 1
                else:
                    if arg_name in argspec.kwonlydefaults:
                        converted_args.append(argspec.kwonlydefaults[arg_name])
                    else:
                        raise TypeError(f"Не передан обязательный ключевой аргумент {arg_name}")
            return converted_args
        else:
            return []

    def convert_args(self, args: Sequence[str]) -> list[Any]:
        argspec, argspec_args = self._get_argspec()
        converted_args, args_index = self._convert_positional_args(args, argspec, argspec_args)
        converted_varargs = self._convert_varargs(args, argspec, args_index)
        converted_kwonlyargs = self._convert_kwonlyargs(args, argspec, args_index)
        converted_args.extend(converted_varargs)
        converted_args.extend(converted_kwonlyargs)
        return converted_args

    def execute(self, *args) -> Any | Text:
        try:
            converted_args = self.convert_args(args) if self.arg_number else args
            return self.action(*converted_args)
        except (ValueError, TypeError) as ex:
            result = Text(f"{ex}\n", style="red")
            if self.usage:
                result.append("Usage: ", style="green")
                result.append(f"{self.usage}", style="white")
            Console().print(result)
            return None
