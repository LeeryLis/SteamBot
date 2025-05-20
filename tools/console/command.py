import copy
import inspect
from typing import Callable, Any, Sequence
from rich.text import Text
from rich.console import Console
from tools.console.param import Param
from tools.console.param_type import ParamType


class Command:
    def __init__(
            self,
            *,
            action: Callable[..., Any],
            aliases: list[str],
            description: str,
            usage: str,
            print_result: bool,
            params: dict[str, Param]
    ) -> None:
        self.action = action
        self.aliases = aliases
        self.description = description
        self.usage = usage
        self.print_result = print_result
        self.params = params

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
            if varargs_annotation:
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

    def get_params(self, args: Sequence[str]
                   ) -> tuple[dict[ParamType, list[tuple[Param, Sequence[str]]]], Sequence[str]]:
        # Разбор переданных аргументов для нахождения параметров и их аргументов
        used_params: dict[ParamType, list[tuple[Param, Sequence[str]]]] = {
            ParamType.ARG_MODIFY: [], ParamType.RESULT_MODIFY: [],
            ParamType.NO_MODIFY: [], ParamType.LOGIC: []}
        new_args = list(copy.copy(args))
        i = 0
        while i < len(new_args):
            arg = new_args[i]
            if param := self.params.get(arg):
                if param.arg_number > 0:
                    param_args = new_args[i + 1:i + param.arg_number + 1]
                    used_params[param.param_type].append((param, param_args))
                    del new_args[i + 1:i + param.arg_number + 1]
                else:
                    used_params[param.param_type].append((param, ''))
                del new_args[i]
            else:
                i += 1
        return used_params, tuple(new_args)

    def execute(self, *args) -> Any:
        try:
            if not self.params:
                return self.action(*self.convert_args(args)) if args else self.action()

            used_params, args = self.get_params(args)
            converted_args = args

            if not used_params[ParamType.LOGIC]:
                converted_args = self.convert_args(args)

            # Параметры, модифицирующие переданные аргументы
            for param, param_args in used_params[ParamType.ARG_MODIFY]:
                converted_args = param.execute(*param_args, *converted_args)

            # Параметры, изменяющие основную логику
            result = None
            if used_params[ParamType.LOGIC]:
                for param, param_args in used_params[ParamType.LOGIC]:
                    result = param.execute(*param_args, *converted_args)
            else:
                result = self.action(*converted_args)

            # Параметры, модифицирующие результат
            for param, param_args in used_params[ParamType.RESULT_MODIFY]:
                result = param.execute(*param_args, result)

            # Параметры, ничего не модифицирующие
            for param, param_args in used_params[ParamType.NO_MODIFY]:
                param.execute(*param_args, *converted_args)

            return result
        except (ValueError, TypeError) as ex:
            result = Text(f"{ex}\n", style="red")
            result.append("Usage: ", style="green")
            result.append(f"{self.usage}", style="white")
            Console().print(result)
            return None
