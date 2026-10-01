from importlib import import_module
from pkgutil import walk_packages
from types import ModuleType

from bot.base.imports import commands, logger

COMMANDS_PACKAGE = "bot.extensions.information.commands"
registered_commands: list[str] = []


def _command_modules() -> list[ModuleType]:
    package = import_module(COMMANDS_PACKAGE)
    module_names = sorted(
        module_info.name
        for module_info in walk_packages(
            package.__path__,
            prefix=f"{package.__name__}.",
        )
        if not module_info.ispkg
    )
    return [import_module(module_name) for module_name in module_names]


async def setup(bot: commands.Bot) -> None:
    for module in _command_modules():
        module_commands = sorted(
            (
                command
                for command in vars(module).values()
                if isinstance(command, commands.Command)
                and command.callback.__module__ == module.__name__
            ),
            key=lambda command: command.name,
        )
        for command in module_commands:
            bot.add_command(command)
            registered_commands.append(command.name)
            logger.info("Loaded command {} from {}", command.name, module.__name__)


async def teardown(bot: commands.Bot) -> None:
    for command_name in registered_commands:
        bot.remove_command(command_name)
    registered_commands.clear()
