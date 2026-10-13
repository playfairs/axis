from __future__ import annotations

import inspect
import re
from collections import defaultdict
from difflib import get_close_matches
from typing import TYPE_CHECKING, get_args, get_origin

from bot.base.imports import commands

EXAMPLE_USER_ID = "1426711359059394662"
EXAMPLE_SNOWFLAKE_ID = "1234567890123456789"
EXAMPLE_ARGUMENT_VALUES = {
    "member": (EXAMPLE_USER_ID, "example_user"),
    "user": (EXAMPLE_USER_ID, "example_member"),
    "user_id": (EXAMPLE_USER_ID,),
    "target": ("Example Role",),
    "role": ("Example Role",),
    "role_input": ("Example Role",),
    "name": ("example-name",),
    "new_name": ("example-name",),
    "nickname": ("example-name",),
    "username": ("example-user",),
    "command_name": ("example-command",),
    "perms": ("8",),
    "permissions": ("8",),
    "color": (
        "Purple",
        "purple",
        "0xC4A7E7",
        "#C4A7E7",
        "C4A7E7",
        "CAE",
    ),
    "colour": (
        "Purple",
        "purple",
        "0xC4A7E7",
        "#C4A7E7",
        "C4A7E7",
        "CAE",
    ),
    "target_or_name": ("#general",),
}
EXAMPLE_TYPE_VALUES = {
    str: ("example",),
    int: ("1",),
    float: ("1.5",),
    bool: ("true",),
}
TRANSFORMER_TYPE_VALUES = {
    "string": EXAMPLE_TYPE_VALUES[str],
    "integer": EXAMPLE_TYPE_VALUES[int],
    "number": EXAMPLE_TYPE_VALUES[float],
    "boolean": EXAMPLE_TYPE_VALUES[bool],
}
CONVERTER_LABELS = {
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
CONVERTER_EXAMPLE_VALUES = {
    "RoleConverter": ("Example Role",),
    "MemberConverter": (EXAMPLE_USER_ID, "example-user"),
    "UserConverter": (EXAMPLE_USER_ID, "example-user"),
    "GuildConverter": ("Example Server",),
    "TextChannelConverter": ("#general",),
    "VoiceChannelConverter": ("Example Voice Channel",),
    "CategoryChannelConverter": ("Example Category",),
}
ANNOTATION_EXAMPLE_VALUES = {
    "Role": ("Example Role",),
    "Member": (EXAMPLE_USER_ID, "example-user"),
    "User": (EXAMPLE_USER_ID, "example-user"),
    "Guild": ("Example Server",),
    "TextChannel": ("#general",),
    "VoiceChannel": ("Example Voice Channel",),
    "CategoryChannel": ("Example Category",),
}
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
        choices = _parameter_choices(command, name)
        if choices:
            line += f"; choices: {', '.join(f'`{choice}`' for choice in choices)}"
        parameters.append(line)
    return parameters


def _parameter_type_name(annotation: object, converter: object) -> str:
    if isinstance(converter, type):
        for base in converter.__mro__:
            if base.__name__ in CONVERTER_LABELS:
                return CONVERTER_LABELS[base.__name__]

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


def _application_parameter(command: commands.Command, name: str) -> object | None:
    app_command = getattr(command, "app_command", None)
    parameters = getattr(app_command, "parameters", ())
    return next(
        (parameter for parameter in parameters if parameter.name == name),
        None,
    )


def _parameter_choices(command: commands.Command, name: str) -> tuple[str, ...]:
    parameter = _application_parameter(command, name)
    choices = getattr(parameter, "choices", ())
    return tuple(str(choice.value) for choice in choices)


def _description_examples(description: str) -> tuple[str, ...]:
    code_examples = re.findall(r"`([^`]+)`", description)
    if code_examples:
        return tuple(code_examples)

    examples = re.search(
        r"\bsuch as\s+(.+?)(?:[.;]|$)",
        description,
        re.IGNORECASE,
    )
    if examples is None:
        return ()
    return tuple(
        value.strip(" `\"'")
        for value in re.split(r",\s*(?:or\s+)?|\s+or\s+", examples.group(1))
        if value.strip(" `\"'")
    )


def _parameter_examples(
    command: commands.Command,
    name: str,
) -> tuple[str, ...]:
    app_parameter = _application_parameter(command, name)
    description = getattr(app_parameter, "description", "")
    documented_examples = _description_examples(description)
    if documented_examples:
        return documented_examples

    choices = _parameter_choices(command, name)
    if choices:
        return choices

    normalized = name.casefold()
    if normalized in EXAMPLE_ARGUMENT_VALUES:
        return EXAMPLE_ARGUMENT_VALUES[normalized]
    if normalized == "id" or normalized.endswith("_id"):
        return (EXAMPLE_SNOWFLAKE_ID,)

    parameter = command.clean_params.get(name)
    if parameter is not None:
        converter = parameter.converter
        for base in getattr(converter, "__mro__", ()):
            if base.__name__ in CONVERTER_EXAMPLE_VALUES:
                return CONVERTER_EXAMPLE_VALUES[base.__name__]

        annotation = parameter.annotation
        if annotation is not inspect.Parameter.empty:
            origin = get_origin(annotation)
            annotation_types = (
                get_args(annotation) if origin is not None else (annotation,)
            )
            for annotation_type in annotation_types:
                transformed_type = getattr(annotation_type, "type", None)
                transformer_examples = TRANSFORMER_TYPE_VALUES.get(
                    getattr(transformed_type, "name", "")
                )
                if transformer_examples is not None:
                    return transformer_examples
                if isinstance(annotation_type, type):
                    examples = ANNOTATION_EXAMPLE_VALUES.get(
                        annotation_type.__name__
                    )
                    if examples is not None:
                        return examples
                if annotation_type in EXAMPLE_TYPE_VALUES:
                    return EXAMPLE_TYPE_VALUES[annotation_type]
        if not parameter.required and parameter.default is not None:
            return (str(parameter.default),)
    return ("example",)


def _example_value(command: commands.Command, name: str) -> str:
    return _parameter_examples(command, name)[0]


def _single_command_example(
    command: commands.Command,
    prefix: str,
    *,
    values: dict[str, str] | None = None,
    through_parameter: int | None = None,
) -> str:
    arguments: list[str] = []
    for index, (name, parameter) in enumerate(command.clean_params.items()):
        if through_parameter is not None and index > through_parameter:
            break
        if parameter.required or through_parameter is not None:
            arguments.append(
                values.get(name, _example_value(command, name))
                if values is not None
                else _example_value(command, name)
            )
    return " ".join((prefix + command.qualified_name, *arguments))


def _command_examples(command: commands.Command, prefix: str) -> list[str]:
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

    parameters = list(command.clean_params.items())
    for index, (name, parameter) in enumerate(parameters):
        values = _parameter_examples(command, name)
        if parameter.required:
            for value in values[1:]:
                examples.append(
                    _single_command_example(command, prefix, values={name: value})
                )
        else:
            if _parameter_choices(command, name):
                continue
            for value in values:
                examples.append(
                    _single_command_example(
                        command,
                        prefix,
                        values={name: value},
                        through_parameter=index,
                    )
                )

    return list(dict.fromkeys(examples))