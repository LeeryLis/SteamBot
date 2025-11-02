from abc import ABC
from tools.console import ConsoleManager
from tools.console import register_commands

class BasicConsole(ABC):
    def run(self, name: str) -> None:
        console_manager = ConsoleManager(name)
        register_commands(self, console_manager)
        console_manager.run()
