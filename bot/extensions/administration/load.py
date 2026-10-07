# This file is part of Axis.
#
# Copyright (c) 2026 playfairs
#
# This work is released into the public domain under the Unlicense.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# See the UNLICENSE file for details.

# Extension Load Manager
# This file loads all commands recursively from
# the path listed in COMMANDS_PACKAGE, the loader
# is reusable, so long as the COMMANDS_PACKAGE path
# is changed.

from importlib import import_module
from pkgutil import walk_packages
from types import ModuleType

from bot.base.imports import commands, logger

COMMANDS_PACKAGE = "bot.extensions.administration.commands"
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
                and command.parent is None
            ),
            key=lambda command: command.name,
        )
        for command in module_commands:
            bot.add_command(command)
            registered_commands.append(command.name)
            logger.info(f"Loaded command {command.name} from {module.__name__}")


async def teardown(bot: commands.Bot) -> None:
    for command_name in registered_commands:
        bot.remove_command(command_name)
    registered_commands.clear()
