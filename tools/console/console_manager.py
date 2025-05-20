import shlex
from typing import Callable, Any

from rich.console import Console
from rich.table import Table
from rich.text import Text

from tools.console import Command, Param, ParamType


class ConsoleManager:
    def __init__(self, name: str) -> None:
        self.name = name
        self.is_running = True
        self.commands: dict[str, Command] = {}

        self.console = Console()

        self.register_command(
            self.stop,
            ["s", "stop"],
            "Stop this console manager",
            print_result=False
        )
        self.register_command(
            self._print_help,
            ["h", "help"],
            "Show help",
            "help [command] [param]",
            params={
                "-p": Param(
                    action=self._print_help_all_params,
                    description="Show help for all params of chosen command",
                    usage="help -p <command>",
                    param_type=ParamType.LOGIC,
                    arg_number=1
                )
            }
        )

    def _get_help_aliases(self) -> str:
        for command in self.commands.values():
            if command.action == self._print_help:
                return ", ".join(command.aliases)
        return ""

    def _print_help_all_params(self, command_name: str) -> Table | Text:
        command = self.commands.get(command_name)

        if not command:
            return Text("No such command", style="red")

        if not command.params:
            return Text("No any params")

        table = Table(title=f"{command_name} params", show_lines=True)
        table.add_column("Alias", style="cyan")
        table.add_column("Description", style="magenta")
        table.add_column("Usage", style="green")

        for alias, param in command.params.items():
            description = param.description
            usage_text = Text(param.usage) or "N/A"

            table.add_row(alias, description, usage_text)
        return table

    def _print_help(self, *args: str) -> Table | Text:
        def print_help_for_all() -> Table:
            table = Table(title="Available commands", show_lines=True)
            table.add_column("Aliases", style="cyan")
            table.add_column("Description", style="magenta")
            table.add_column("Usage", style="green")
            table.add_column("Params", style="yellow")

            printed_commands = set()
            for helped_command in self.commands.values():
                if helped_command in printed_commands:
                    continue
                aliases = ", ".join(helped_command.aliases)
                description = helped_command.description
                usage_text = Text(helped_command.usage) or "N/A"
                params_text = ", ".join(helped_command.params) if helped_command.params else "N/A"

                table.add_row(aliases, description, usage_text, params_text)
                printed_commands.add(helped_command)
            return table

        def print_help_for_command() -> Text | list[Text]:
            result = Text()

            command_name = args[0]
            helped_command = self.commands.get(command_name)

            if not helped_command:
                return Text(f"No such command: {command_name}", style="red")

            aliases = ", ".join(helped_command.aliases)
            result.append("Command: ", style="cyan")
            result.append(f"{aliases}")

            if helped_command.description:
                result.append("\nDescription: ", style="magenta")
                result.append(f"{helped_command.description}")

            if helped_command.usage:
                result.append("\nUsage: ", style="green")
                result.append(f"{helped_command.usage}")

            if helped_command.params:
                result.append(Text("\nParams: ", style="yellow"))
                result.append(Text(f"{', '.join(helped_command.params)}"))

            return result

        def print_help_for_command_param() -> Text | list[Text]:
            command_name = args[0]
            helped_command = self.commands.get(command_name)

            if not helped_command:
                return Text(f"No such command: {command_name}", style="red")

            if not helped_command.params:
                return Text(f"The command {command_name} has no any params", style="red")

            param_name = args[1]
            param = helped_command.params.get(param_name)

            if not param:
                return Text(f"The command {command_name} has no such param: {param_name}", style="red")

            result = Text()

            aliases = ", ".join(helped_command.aliases)
            result.append("Command: ", style="cyan")
            result.append(f"{aliases}")

            result.append("\nParam: ", style="yellow")
            result.append(f"{param_name}")

            result.append("\nDescription: ", style="magenta")
            result.append(f"{param.description}")

            if param.usage:
                result.append("\nUsage: ", style="green")
                result.append(f"{param.usage}")

            return result

        if len(args) == 0:
            return print_help_for_all()
        elif len(args) == 1:
            return print_help_for_command()
        elif len(args) == 2:
            return print_help_for_command_param()
        else:
            return Text("Too much arguments.", style="red")

    def register_command(
            self,
            action: Callable[..., Any],
            aliases: list[str],
            description: str,
            usage: str = "",
            print_result: bool = True,
            params: dict[str, Param] = None
    ) -> None:
        command = Command(
            action=action, aliases=aliases, description=description,
            usage=usage, print_result=print_result, params=params)
        for alias in aliases:
            self.commands[alias] = command

    def stop(self) -> None:
        self.is_running = False

    def run(self) -> None:
        self.is_running = True
        while self.is_running:
            command_line = input(f"\n{self.name}: ").strip()
            if not command_line:
                continue

            command_name, *args = shlex.split(command_line)

            command_obj = self.commands.get(command_name)
            if not command_obj:
                self.console.print(
                    Text(f"Unknown command. Type {self._get_help_aliases()} for available commands.", style="red")
                )
                continue

            result = command_obj.execute(*args)
            if command_obj.print_result and result:
                self.console.print(result)
