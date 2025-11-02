import shlex
from typing import Callable

from tools.console import Command
from rich.console import Console
from rich.text import Text
from rich.table import Table

from tools.console import command
from tools.console import register_commands
from tools import escape_brackets


class ConsoleManager:
    def __init__(self, name="console"):
        self.commands = {}
        self.name = name
        self.is_running = False
        self.console = Console()

        register_commands(self, self)

    def register_command(
            self, *,
            action: Callable, aliases: list, description: str, usage: str,
            flag_aliases: dict = None, flag_descriptions: dict = None
    ):
        cmd_obj = Command(
            action=action,
            aliases=aliases,
            description=description,
            usage=usage,
            flag_aliases=flag_aliases or {},
            flag_descriptions=flag_descriptions or {}
        )
        for alias in [cmd_obj.aliases[0]] + cmd_obj.aliases[1:]:
            self.commands[alias] = cmd_obj

    def run(self):
        self.is_running = True
        while self.is_running:
            command_line = input(f"\n{self.name}: ").strip()
            if not command_line:
                continue

            try:
                command_name, *args = shlex.split(command_line)
            except ValueError as ex:
                self.console.print(f"[red]Error parsing command: {ex}[/red]")
                continue

            command_obj = self.commands.get(command_name)
            if not command_obj:
                self.console.print(Text(f"Unknown command. Type 'help' for available commands.", style="red"))
                continue

            command_obj.execute(*args)

    @command(
        aliases=["exit", "stop", "quit", "s"],
        description="Stop Console Manager",
        usage="stop"
    )
    def _stop(self) -> None:
        self.is_running = False

    @command(
        aliases=["help", "h"],
        description="Show help for all commands or entered command",
        usage="help [command]"
    )
    def _show_help(self, *args: str) -> None:
        def collect_flags(cmd: Command, use_spaces: bool = False) -> str:
            result = []
            aliases_by_param = {}

            for alias, param_name in cmd.flag_aliases.items():
                aliases_by_param.setdefault(param_name, []).append(alias)

            for param_name, description in cmd.flag_descriptions.items():
                aliases = aliases_by_param.get(param_name)
                alias_str = ", ".join(aliases)
                result.append(f"{alias_str}: {description}")
                if use_spaces:
                    result[-1] = " "*2 + result[-1]

            return "\n".join(result)

        def print_help_for_all() -> Table:
            table = Table(title="Available commands", show_lines=True)
            table.add_column("Aliases", style="cyan")
            table.add_column("Description", style="magenta")
            table.add_column("Usage", style="green")
            table.add_column("Params", style="yellow")

            printed_commands = set()
            for cmd in self.commands.values():
                if cmd in printed_commands:
                    continue
                aliases = ", ".join(cmd.aliases)
                description = cmd.description
                usage = escape_brackets(cmd.usage) or "N/A"
                flags = "N/A"
                if cmd.flag_aliases:
                    flags = collect_flags(cmd)
                table.add_row(aliases, description, usage, flags)
                printed_commands.add(cmd)
            return table

        def print_help_for_command() -> Text:
            cmd_name = args[0]
            cmd: Command = self.commands.get(cmd_name)
            if not cmd:
                return Text(f"No such command: {cmd_name}", style="red")

            result = Text()
            result.append(f"Command: {', '.join(cmd.aliases)}\n", style="cyan")
            result.append(f"Description: {cmd.description}\n", style="magenta")
            result.append(f"Usage: {cmd.usage}", style="green")

            if cmd.flag_aliases:
                result.append("\nFlags:\n", style="yellow")
                result.append(collect_flags(cmd, use_spaces=True), style="yellow")

            return result

        if len(args) == 0:
            self.console.print(print_help_for_all())
        elif len(args) == 1:
            self.console.print(print_help_for_command())
        else:
            self.console.print(Text("Too many arguments.", style="red"))
