from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from discord.ext import commands

FIELD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)*\Z")
SUPPORTED_ROOTS = {
    "user",
    "member",
    "guild",
    "server",
    "channel",
    "invite",
    "bot",
}


def _parse_template(source: str) -> list[tuple[str, str | None]]:
    parts: list[tuple[str, str | None]] = []
    literal: list[str] = []
    index = 0

    def flush_literal() -> None:
        if literal:
            parts.append(("".join(literal), None))
            literal.clear()

    while index < len(source):
        char = source[index]
        if source.startswith("{{", index):
            literal.append("{")
            index += 2
            continue
        if source.startswith("}}", index):
            literal.append("}")
            index += 2
            continue
        if char == "}":
            raise MessageTemplateError(
                "Invalid message template: unexpected '}' outside a field."
            )
        if char != "{":
            literal.append(char)
            index += 1
            continue

        flush_literal()
        end = source.find("}", index + 1)
        if end == -1:
            raise MessageTemplateError(
                "Invalid message template: missing '}' after a field."
            )
        field_name = source[index + 1 : end]
        if "{" in field_name or not FIELD_PATTERN.fullmatch(field_name):
            raise MessageTemplateError(
                f"Invalid template field {{{field_name}}}. Use "
                "names like {user.mention} or {guild.name}."
            )
        root = field_name.split(".", 1)[0]
        if root not in SUPPORTED_ROOTS:
            raise MessageTemplateError(
                f"Unknown template object {{{root}}}. Supported objects "
                "include user, guild, channel, invite, and bot."
            )
        parts.append(("", field_name))
        index = end + 1

    flush_literal()
    return parts


class MessageTemplateError(commands.BadArgument):
    pass


@dataclass(frozen=True, slots=True)
class MessageTemplate:
    source: str
    fields: tuple[str, ...]

    def render(self, **context: Any) -> str:
        values = dict(context)
        if "member" not in values and "user" in values:
            values["member"] = values["user"]
        if "user" not in values and "member" in values:
            values["user"] = values["member"]
        if "server" not in values and "guild" in values:
            values["server"] = values["guild"]
        if "guild" not in values and "server" in values:
            values["guild"] = values["server"]

        output: list[str] = []
        for literal, field_name in _parse_template(self.source):
            output.append(literal)
            if field_name is not None:
                output.append(_resolve_field(field_name, values))
        return "".join(output)


def _resolve_field(field_name: str, values: Mapping[str, Any]) -> str:
    parts = field_name.split(".")
    current = values.get(parts[0])
    if current is None:
        raise MessageTemplateError(
            f"No value is available for {{{field_name}}}."
        )

    if parts[0] in {"guild", "server"} and parts[1:] == ["members"]:
        member_count = getattr(current, "member_count", None)
        if member_count is None:
            members = getattr(current, "members", None)
            if members is not None:
                member_count = len(members)
        if member_count is None:
            raise MessageTemplateError(
                f"The member count isn't available for {{{field_name}}}."
            )
        return str(member_count)

    for attribute in parts[1:]:
        if attribute.startswith("_"):
            raise MessageTemplateError(
                f"Private attributes aren't available in {{{field_name}}}."
            )
        if isinstance(current, Mapping):
            current = current.get(attribute)
        else:
            current = getattr(current, attribute, None)
        if current is None:
            raise MessageTemplateError(
                f"Unknown or unavailable template value {{{field_name}}}."
            )
        if callable(current):
            raise MessageTemplateError(
                f"Methods aren't available in {{{field_name}}}."
            )

    if isinstance(current, (str, int, float, bool)):
        return str(current)
    if hasattr(current, "isoformat"):
        return current.isoformat()
    raise MessageTemplateError(
        f"Template value {{{field_name}}} can't be converted to text."
    )


class MessageTemplateConverter(commands.Converter[MessageTemplate]):
    async def convert(
        self,
        ctx: commands.Context,
        argument: str,
    ) -> MessageTemplate:
        del ctx
        fields = [
            field_name
            for _, field_name in _parse_template(argument)
            if field_name is not None
        ]
        return MessageTemplate(argument, tuple(fields))
