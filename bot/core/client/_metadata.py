from __future__ import annotations

import inspect
from collections import defaultdict
from difflib import get_close_matches
from typing import TYPE_CHECKING, get_args, get_origin

from bot.base.imports import commands

EXAMPLE_USER_ID = "1426711359059394662"
EXAMPLE_USER_NAME = "playfairs"
EXAMPLE_SNOWFLAKE_ID = "1234567890123456789"
USER_TARGET_ARGUMENTS = frozenset({"member", "user", "user_id"})
__all__ = (
    "_category_name",
    "_command_examples",
    "_command_names",
    "_command_suggestion",
    "_description",
    "_example_value",
    "_extension_category",
    "_is_owner_command",
    "_parameter_details",
    "_permission_requirements",
    "_root_commands",
    "_single_command_example",
    "_source_link",
)

if TYPE_CHECKING:
    from collections.abc import Iterable


def _category_name(command: commands.Command) -> str:
    module = command.callback.__module__
    prefix = "bot.extensions."
    if module.startswith(prefix):
        extension = module[len(prefix) :].partition(".")[0]
        return extension.replace("_", " ").title()
    return "Core"


def _is_owner_command(command: commands.Command) -> bool:
    return command.callback.__module__.startswith("bot.extensions.owner.")


def _extension_category(
    bot: commands.Bot,
    extension_name: str,
) -> str | None:
    if any(character.isspace() for character in extension_name):
        return None

    prefix = "bot.extensions."
    matches = {
        extension[len(prefix) :].partition(".")[0]
        for extension in bot.extensions
        if extension.startswith(prefix)
        and extension[len(prefix) :].partition(".")[0].casefold()
        == extension_name.casefold()
    }
    if len(matches) != 1:
        return None
    return next(iter(matches)).replace("_", " ").title()


def _root_commands(
    bot: commands.Bot,
    *,
    include_owner_commands: bool,
) -> dict[str, list[commands.Command]]:
    categories: dict[str, list[commands.Command]] = defaultdict(list)
    for command in bot.commands:
        if command.parent is not None or command.hidden:
            continue
        if command.cog_name == "Jishaku":
            continue
        if not include_owner_commands and _is_owner_command(command):
            continue
        categories[_category_name(command)].append(command)

    return {
        category: sorted(commands_, key=lambda command: command.name.casefold())
        for category, commands_ in sorted(categories.items())
    }


def _command_names(commands_: Iterable[commands.Command]) -> list[str]:
    return sorted(
        (
            f"{command.name}{'*' if isinstance(command, commands.Group) else ''}"
            for command in commands_
        ),
        key=str.casefold,
    )


def _permission_requirements(command: commands.Command) -> list[str]:
    user_permissions: set[str] = set()
    bot_permissions: set[str] = set()
    guild_only = False

    for check in command.checks:
        qualname = getattr(check, "__qualname__", "")
        if "guild_only" in qualname:
            guild_only = True
        if not inspect.isfunction(check):
            continue
        if "has_guild_permissions" not in qualname:
            continue

        permissions = inspect.getclosurevars(check).nonlocals.get("perms", {})
        if not isinstance(permissions, dict):
            continue
        destination = (
            bot_permissions
            if "bot_has_guild_permissions" in qualname
            else user_permissions
        )
        destination.update(
            permission.replace("_", " ").title()
            for permission, enabled in permissions.items()
            if enabled
        )

    result: list[str] = []
    if guild_only:
        result.append("Server only")
    if user_permissions:
        result.append(f"User: {', '.join(sorted(user_permissions))}")
    if bot_permissions:
        result.append(f"Bot: {', '.join(sorted(bot_permissions))}")
    return result


def _parameter_details(command: commands.Command) -> list[str]:
    parameters: list[str] = []
    for name, parameter in command.clean_params.items():
        status = "required" if parameter.required else "optional"
        type_name = _parameter_type_name(
            parameter.annotation,
            parameter.converter,
        )
        line = f"`{name}` — {status}, {type_name}"
        if not parameter.required:
            line += f"; default: `{parameter.default}`"
        parameters.append(line)
    return parameters


def _parameter_type_name(annotation: object, converter: object) -> str:
    converter_labels = {
        "RoleConverter": "Role",
        "MemberConverter": "Member",
        "UserConverter": "User",
        "GuildConverter": "Server",
        "TextChannelConverter": "Text channel",
        "VoiceChannelConverter": "Voice channel",
        "CategoryChannelConverter": "Category",
        "ColourConverter": "Color",
        "ColorConverter": "Color",
        "InviteConverter": "Invite",
        "EmojiConverter": "Emoji",
        "PartialEmojiConverter": "Emoji",
    }
    if isinstance(converter, type):
        for base in converter.__mro__:
            if base.__name__ in converter_labels:
                return converter_labels[base.__name__]

    if annotation is inspect.Parameter.empty:
        return "value"
    if annotation is type(None):
        return "None"

    origin = get_origin(annotation)
    if origin is not None:
        return " | ".join(
            _parameter_type_name(argument, argument)
            for argument in get_args(annotation)
        )

    type_labels = {
        str: "Text",
        int: "Integer",
        float: "Number",
        bool: "Boolean",
    }
    if isinstance(annotation, type) and annotation in type_labels:
        return type_labels[annotation]
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation)


def _description(command: commands.Command) -> str:
    description = (
        command.description
        or command.help
        or command.brief
        or inspect.getdoc(command.callback)
    )
    app_command = getattr(command, "app_command", None)
    if not description and app_command is not None:
        description = app_command.description
    return description or "No description has been provided for this command yet."


def _source_link(module: str) -> str:
    path = module.replace(".", "/") + ".py"
    return f"[`{module}`](<https://github.com/playfairs/axis/blob/master/{path}>)"


def _command_suggestion(
    bot: commands.Bot,
    query: str,
    *,
    include_owner_commands: bool,
) -> str | None:
    candidates: set[str] = set()
    for command in bot.walk_commands():
        if command.hidden or command.cog_name == "Jishaku":
            continue
        if not include_owner_commands and _is_owner_command(command):
            continue
        candidates.add(command.qualified_name)
        candidates.update(
            f"{command.parent.qualified_name} {alias}"
            if command.parent is not None
            else alias
            for alias in command.aliases
        )
    return next(
        iter(get_close_matches(query.casefold(), sorted(candidates), n=1, cutoff=0.6)),
        None,
    )


def _example_value(command: commands.Command, name: str) -> str:
    normalized = name.casefold()
    if normalized in {"member", "user"}:
        return EXAMPLE_USER_ID
    if normalized in {"target", "role", "role_input"}:
        return "Swag"
    if normalized == "user_id":
        return EXAMPLE_USER_ID
    if normalized == "id" or normalized.endswith("_id"):
        return EXAMPLE_SNOWFLAKE_ID
    if normalized == "target_or_name":
        return "#general"
    if normalized in {"name", "new_name"}:
        return "amazing-name"
    if normalized in {"color", "colour"}:
        return "Purple"
    if normalized == "username":
        return EXAMPLE_USER_NAME
    if normalized == "command_name":
        return "role create"
    parameter = command.clean_params.get(name)
    if parameter is not None and not parameter.required:
        return str(parameter.default)
    return "example"


def _single_command_example(
    command: commands.Command,
    prefix: str,
    *,
    user_target: str | None = None,
) -> str:
    arguments: list[str] = []
    for name, parameter in command.clean_params.items():
        if name.casefold() in USER_TARGET_ARGUMENTS and user_target is not None:
            arguments.append(user_target)
        elif parameter.required:
            arguments.append(_example_value(command, name))
    return " ".join((prefix + command.qualified_name, *arguments))


def _command_examples(command: commands.Command, prefix: str) -> list[str]:
    if command.qualified_name == "nickknock interval":
        return [
            f"{prefix}nickknock interval 30seconds",
            f"{prefix}nickknock interval 5m",
            f"{prefix}nickknock interval 2hours",
        ]

    examples = [_single_command_example(command, prefix)]
    if isinstance(command, commands.Group):
        examples.extend(
            example
            for child in sorted(
                (child for child in command.commands if not child.hidden),
                key=lambda child: child.name.casefold(),
            )
            for example in _command_examples(child, prefix)
        )
    elif command.qualified_name == "role create":
        examples.extend(
            (
                f"{prefix}role create moderators perms=8",
                f"{prefix}role create pastel color=yellow",
                f"{prefix}role create pastel perms=8 color=C4A7E7",
                f"{prefix}role create pastel perms=8 color=#C4A7E7",
                f"{prefix}role create pastel perms=8 color=0xC4A7E7",
                f"{prefix}role create pastel perms=8 color=CAE",
                f"{prefix}role create pastel perms=8 color=Purple",
                f"{prefix}role create pastel perms=8 color=purple",
            )
        )
    elif any(
        name.casefold() in USER_TARGET_ARGUMENTS
        for name in command.clean_params
    ):
        examples.extend(
            _single_command_example(command, prefix, user_target=user_target)
            for user_target in (EXAMPLE_USER_ID, EXAMPLE_USER_NAME)
        )
    elif any(not parameter.required for parameter in command.clean_params.values()):
        arguments = [
            _example_value(command, name)
            for name, parameter in command.clean_params.items()
            if parameter.required or parameter.default is not None
        ]
        examples.append(" ".join((prefix + command.qualified_name, *arguments)))
    return list(dict.fromkeys(examples))