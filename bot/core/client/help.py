from __future__ import annotations

import inspect
from collections import defaultdict
from difflib import get_close_matches
from typing import TYPE_CHECKING, get_args, get_origin

from bot.base.imports import (
    DEFAULT_CONTAINER_COLOR,
    app_commands,
    commands,
    discord,
    logger,
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


def _root_commands(bot: commands.Bot) -> dict[str, list[commands.Command]]:
    categories: dict[str, list[commands.Command]] = defaultdict(list)
    for command in bot.commands:
        if command.parent is not None or command.hidden:
            continue
        if command.cog_name == "Jishaku":
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
    description = command.help or command.brief or inspect.getdoc(command.callback)
    app_command = getattr(command, "app_command", None)
    if not description and app_command is not None:
        description = app_command.description
    return description or "No description has been provided for this command yet."


def _resolve_command(
    bot: commands.Bot,
    command_path: str,
) -> commands.Command | None:
    command, _ = _resolve_command_reference(bot, command_path)
    return command


def _resolve_command_reference(
    bot: commands.Bot,
    command_path: str,
) -> tuple[commands.Command | None, str | None]:
    parts = command_path.split()
    if not parts:
        return None, None

    command = bot.get_command(parts[0])
    alias_used = (
        parts[0]
        if command is not None and parts[0].casefold() != command.name.casefold()
        else None
    )
    for part in parts[1:]:
        if not isinstance(command, commands.Group):
            return None, None
        command = command.get_command(part)
        if command is None:
            return None, None
        if part.casefold() != command.name.casefold() and alias_used is None:
            alias_used = part
    return command, alias_used


def _source_link(module: str) -> str:
    path = module.replace(".", "/") + ".py"
    return f"[`{module}`](<https://github.com/playfairs/axis/blob/master/{path}>)"


def _command_suggestion(bot: commands.Bot, query: str) -> str | None:
    candidates: set[str] = set()
    for command in bot.walk_commands():
        if command.hidden or command.cog_name == "Jishaku":
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


def _command_details(
    command: commands.Command,
    prefix: str,
) -> list[discord.ui.Item]:
    description = _description(command).splitlines()[0]
    signature = f" {command.signature}" if command.signature else ""
    aliases = ", ".join(f"`{alias}`" for alias in command.aliases) or "None"
    permissions = "; ".join(_permission_requirements(command)) or "None"
    cooldown = getattr(command._buckets, "_cooldown", None)
    cooldown_text = (
        f"{cooldown.rate} use(s) per {cooldown.per:g} second(s)"
        if cooldown is not None
        else "None"
    )
    module = command.callback.__module__
    if module.startswith("bot.extensions."):
        extension = _category_name(command)
    else:
        extension = "Axis Core"

    items: list[discord.ui.Item] = [
        discord.ui.TextDisplay(f"## {command.qualified_name}\n{description}"),
        discord.ui.Separator(),
        discord.ui.TextDisplay(
            f"**Aliases:** {aliases}\n"
            f"**Usage:** `{prefix}{command.qualified_name}{signature}`\n"
            f"**Permissions:** {permissions}\n"
            f"**Cooldown:** {cooldown_text}"
        ),
    ]
    parameters = _parameter_details(command)
    if parameters:
        items.extend(
            (
                discord.ui.Separator(),
                discord.ui.TextDisplay("### Arguments\n" + "\n".join(parameters)),
            )
        )
    items.extend(
        (
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"**Extension:** {extension}"),
        )
    )
    return items


class _CategorySelect(discord.ui.Select["HelpView"]):
    def __init__(
        self,
        categories: list[str],
        selected_category: str | None,
    ) -> None:
        options = [
            discord.SelectOption(
                label="Start",
                value="__start__",
                description="Return to the Axis help start menu.",
                default=selected_category is None,
            )
        ]
        options.extend(
            discord.SelectOption(
                label=category,
                value=category,
                description=f"Browse {category} commands.",
                default=category == selected_category,
            )
            for category in categories[:24]
        )
        super().__init__(
            placeholder="Select a category.",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(self.view, HelpView):
            raise TypeError("The help category selector is not attached to HelpView.")
        selected = self.values[0]
        view = HelpView(
            self.view.bot,
            category=None if selected == "__start__" else selected,
        )
        await interaction.response.edit_message(view=view)


class _GroupPageButton(discord.ui.Button["HelpView"]):
    def __init__(self, direction: int, page: int, total_pages: int) -> None:
        self.direction = direction
        label = "Previous" if direction < 0 else "Next"
        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            disabled=(page == 0 if direction < 0 else page + 1 == total_pages),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, HelpView) or not isinstance(
            view.command, commands.Group
        ):
            raise TypeError("Group help pagination button is not attached to a group.")

        page = max(0, min(view.page + self.direction, view.total_pages - 1))
        updated_view = HelpView(
            view.bot,
            command=view.command,
            page=page,
            prefix=view.prefix,
        )
        await interaction.response.edit_message(
            view=updated_view,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class _GroupPageIndicator(discord.ui.Button["HelpView"]):
    def __init__(self, page: int, total_pages: int) -> None:
        super().__init__(
            label=f"{page + 1}/{total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
        )


class HelpView(discord.ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        *,
        category: str | None = None,
        command: commands.Command | None = None,
        command_query: str | None = None,
        page: int = 0,
        prefix: str = ",",
    ) -> None:
        super().__init__(timeout=900)
        self.bot = bot
        self.command = command
        self.prefix = prefix
        subcommands = (
            sorted(
                (child for child in command.commands if not child.hidden),
                key=lambda child: child.name.casefold(),
            )
            if isinstance(command, commands.Group)
            else []
        )
        self.total_pages = len(subcommands) + 1 if subcommands else 1
        self.page = max(0, min(page, self.total_pages - 1))
        categories = _root_commands(bot)
        content: list[discord.ui.Item] = []
        selected_category = category

        if command_query is not None and command is None:
            content.append(
                discord.ui.TextDisplay(
                    f"# Command not found\nNo loaded command matches `{command_query}`."
                )
            )
        elif command is not None:
            selected_category = _category_name(command)
            page_command = command
            if isinstance(command, commands.Group) and self.page > 0:
                page_command = subcommands[self.page - 1]
            try:
                content.extend(_command_details(page_command, prefix))
            except Exception:
                logger.exception(
                    "Failed to render help page for command %s; showing an ellipsis.",
                    page_command.qualified_name,
                )
                content.append(discord.ui.TextDisplay("…"))
        elif category is not None and category in categories:
            category_commands = categories[category]
            names = _command_names(category_commands)
            content.append(discord.ui.TextDisplay(f"```{', '.join(names)}```"))
            count = len(category_commands)
            command_word = "command" if count == 1 else "commands"
            content.append(
                discord.ui.TextDisplay(
                    f"{count} {command_word} — commands with * are groups. "
                    "Running help on them shows subcommands."
                )
            )
        else:
            content.append(
                discord.ui.TextDisplay(
                    "## Axis\n"
                    "Browse the commands currently loaded by **Axis** below.\n"
                    f"> Use `{prefix}h <command>` to see a command's usage, arguments, "
                    "aliases, and permissions.\n"
                    "> `<argument>` is required; `[argument]` is optional.\n\n"
                    "**[Source Code](<https://github.com/playfairs/axis>)**"
                )
            )

        if (
            command_query is None
            and command is None
            and category is None
            and bot.user is not None
        ):
            content[0] = discord.ui.Section(
                content[0],
                accessory=discord.ui.Thumbnail(
                    bot.user.display_avatar.url,
                    description="Axis bot avatar",
                ),
            )

        if command is None and categories:
            content.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.ActionRow(
                        _CategorySelect(list(categories), selected_category)
                    ),
                )
            )

        self.add_item(
            discord.ui.Container(*content, accent_color=DEFAULT_CONTAINER_COLOR)
        )
        if isinstance(command, commands.Group) and subcommands:
            container = self.children[0]
            if not isinstance(container, discord.ui.Container):
                raise TypeError("Command help content is not inside a Container.")
            container.add_item(discord.ui.Separator())
            container.add_item(
                discord.ui.ActionRow(
                    _GroupPageButton(-1, self.page, self.total_pages),
                    _GroupPageIndicator(self.page, self.total_pages),
                    _GroupPageButton(1, self.page, self.total_pages),
                )
            )


@commands.hybrid_command(name="help", aliases=("h",))
@app_commands.describe(command_name="The command to show detailed help for.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def help_command(
    ctx: commands.Context,
    *,
    command_name: str | None = None,
) -> None:
    """Browse loaded Axis commands or show detailed help for one command."""
    command = (
        _resolve_command(ctx.bot, command_name) if command_name is not None else None
    )
    if command_name is not None and command is None:
        suggestion = _command_suggestion(ctx.bot, command_name)
        response = f"Command `{command_name}` does not exist"
        if suggestion is not None:
            response += f", perhaps you meant `{suggestion}`?"
        else:
            response += "."
        await ctx.send(response)
        try:
            await ctx.message.add_reaction("‼️")
        except discord.HTTPException as error:
            logger.warning(
                "Could not react to an unknown help command in channel %s (HTTP %s).",
                ctx.channel.id,
                error.status,
            )
        return
    await ctx.send(
        view=HelpView(
            ctx.bot,
            command=command,
            command_query=command_name,
            prefix=ctx.clean_prefix,
        ),
        allowed_mentions=discord.AllowedMentions.none(),
    )

@commands.command(name="where", aliases=("which",))
async def where_command(
    ctx: commands.Context,
    *,
    command_name: str,
) -> None:
    """Show which loaded extension defines a command."""
    command, alias_used = _resolve_command_reference(ctx.bot, command_name)
    if command is None:
        await ctx.send(f"No loaded command matches `{command_name}`.")
        return

    module = command.callback.__module__
    extension_prefix = "bot.extensions."
    command_name = command.qualified_name
    if alias_used is not None:
        subject = (
            f"`{alias_used}` is an alias for the `{command_name}` command, "
            "which belongs to "
        )
    else:
        subject = f"The `{command_name}` command belongs to "
    source = _source_link(module)
    if module.startswith(extension_prefix):
        extension = module[len(extension_prefix) :].partition(".")[0]
        response = f"{subject}{source}, which is part of the `{extension}` extension."
    else:
        response = f"{subject}{source}, which is part of the **Axis Core**."
    await ctx.send(response)


__all__ = ("HelpView", "help_command", "where_command")
