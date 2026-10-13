from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from bot.core.client import _metadata
from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord, logger

@dataclass(slots=True)
class _GroupPagination:
    page: int
    more_details: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def _command_details(
    command: commands.Command,
    prefix: str,
    *,
    more: bool = False,
) -> list[discord.ui.Item]:
    description = _metadata._description(command).splitlines()[0]
    signature = f" {command.signature}" if command.signature else ""
    parameters = _metadata._parameter_details(command)
    aliases = ", ".join(f"`{alias}`" for alias in command.aliases) or "None"
    permissions = "; ".join(_metadata._permission_requirements(command)) or "None"
    cooldown = getattr(command._buckets, "_cooldown", None)
    cooldown_text = (
        f"{cooldown.rate} use(s) per {cooldown.per:g} second(s)"
        if cooldown is not None
        else "None"
    )
    module = command.callback.__module__
    if module.startswith("bot.extensions."):
        extension = _metadata._category_name(command)
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
    if more:
        command_type = "Command group" if isinstance(command, commands.Group) else "Command"
        slash_command = getattr(command, "app_command", None)
        extra_details = [
            f"**Type:** {command_type}",
            f"**Status:** {'Enabled' if command.enabled else 'Disabled'}",
            f"**Visibility:** {'Hidden' if command.hidden else 'Visible'}",
            f"**Slash command:** {'Available' if slash_command is not None else 'Not available'}",
        ]
        if isinstance(command, commands.Group):
            child_count = sum(not child.hidden for child in command.commands)
            extra_details.append(f"**Subcommands:** {child_count}")
            extra_details.append(
                "**Runs without a subcommand:** "
                f"{'Yes' if command.invoke_without_command else 'No'}"
            )
        items.extend(
            (
                discord.ui.Separator(),
                discord.ui.TextDisplay("### Additional details\n" + "\n".join(extra_details)),
                discord.ui.Separator(),
                discord.ui.TextDisplay(
                    "### Examples\n"
                    + "\n".join(
                        f"`{example}`"
                        for example in _metadata._command_examples(command, prefix)
                    )
                ),
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
            is_bot_owner=self.view.is_bot_owner,
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

        await interaction.response.defer()
        pagination = view.pagination
        async with pagination.lock:
            page = max(0, min(pagination.page + self.direction, view.total_pages - 1))
            if page == pagination.page:
                return
            updated_view = HelpView(
                view.bot,
                command=view.command,
                page=page,
                prefix=view.prefix,
                is_bot_owner=view.is_bot_owner,
                pagination=pagination,
            )
            try:
                await interaction.edit_original_response(
                    view=updated_view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException as error:
                logger.warning(
                    "Could not update help pagination for %s (HTTP %s).",
                    view.command.qualified_name,
                    error.status,
                )
                await interaction.followup.send(
                    "Couldn't update the help page. Please try again.",
                    ephemeral=True,
                )
                return
            pagination.page = page


class _MoreCommandInfoButton(discord.ui.Button["HelpView"]):
    def __init__(self, more_details: bool) -> None:
        self.more_details = more_details
        super().__init__(
            label="Less" if more_details else "More",
            style=discord.ButtonStyle.primary,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if view is None or view.command is None or view.page_command is None:
            raise TypeError("Command detail button is not attached to a command help view.")

        await interaction.response.defer()
        pagination = view.pagination
        async with pagination.lock:
            previous_more_details = pagination.more_details
            pagination.more_details = not previous_more_details
            updated_view = HelpView(
                view.bot,
                command=view.command,
                page=pagination.page,
                prefix=view.prefix,
                is_bot_owner=view.is_bot_owner,
                pagination=pagination,
            )
            try:
                await interaction.edit_original_response(
                    view=updated_view,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException as error:
                pagination.more_details = previous_more_details
                logger.warning(
                    "Could not update help details for %s (HTTP %s).",
                    view.page_command.qualified_name,
                    error.status,
                )
                await interaction.followup.send(
                    "Couldn't update the help details. Please try again.",
                    ephemeral=True,
                )
                return


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
        is_bot_owner: bool = False,
        pagination: _GroupPagination | None = None,
    ) -> None:
        super().__init__(timeout=900)
        self.bot = bot
        self.command = command
        self.prefix = prefix
        self.is_bot_owner = is_bot_owner
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
        self.pagination = pagination or _GroupPagination(self.page)
        self.page_command = (
            subcommands[self.page - 1]
            if isinstance(command, commands.Group) and self.page > 0
            else command
        )
        categories = _metadata._root_commands(
            bot,
            include_owner_commands=is_bot_owner,
        )
        category_commands = categories.get(category) if category is not None else None
        if category == "Owner" and not is_bot_owner:
            category_commands = _metadata._root_commands(
                bot,
                include_owner_commands=True,
            ).get(category)
        category_options = list(categories)
        if category == "Owner" and not is_bot_owner:
            category_options.append(category)
        content: list[discord.ui.Item] = []
        selected_category = category if category in category_options else None

        if command_query is not None and command is None:
            content.append(
                discord.ui.TextDisplay(
                    f"# Command not found\nNo loaded command matches `{command_query}`."
                )
            )
        elif command is not None:
            selected_category = _metadata._category_name(command)
            page_command = self.page_command
            if page_command is None:
                raise RuntimeError("Command help page is missing its command.")
            try:
                content.extend(
                    _command_details(
                        page_command,
                        prefix,
                        more=self.pagination.more_details,
                    )
                )
            except Exception:
                logger.exception(
                    "Failed to render help page for command %s; showing an ellipsis.",
                    page_command.qualified_name,
                )
                content.append(discord.ui.TextDisplay("…"))
        elif category_commands is not None:
            names = _metadata._command_names(category_commands)
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
            command_count = sum(
                1
                for loaded_command in bot.walk_commands()
                if (
                    not loaded_command.hidden
                    and loaded_command.cog_name != "Jishaku"
                    and (
                        is_bot_owner
                        or not _metadata._is_owner_command(loaded_command)
                    )
                )
            )
            content.append(
                discord.ui.TextDisplay(
                    "## Axis\n"
                    "Browse the commands currently loaded by **Axis** below.\n"
                    f"**Total loaded commands:** {command_count}\n\n"
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
                    bot.user.display_avatar.with_size(128).url,
                    description="Axis bot avatar",
                ),
            )

        if command is None and category_options:
            content.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.ActionRow(
                        _CategorySelect(category_options, selected_category)
                    ),
                )
            )

        self.add_item(
            discord.ui.Container(*content, accent_color=DEFAULT_CONTAINER_COLOR)
        )
        if command is not None:
            container = self.children[0]
            if not isinstance(container, discord.ui.Container):
                raise TypeError("Command help content is not inside a Container.")
            controls: list[discord.ui.Item] = []
            if isinstance(command, commands.Group) and subcommands:
                controls.extend(
                    (
                        _GroupPageButton(-1, self.page, self.total_pages),
                        _GroupPageIndicator(self.page, self.total_pages),
                        _GroupPageButton(1, self.page, self.total_pages),
                    )
                )
            controls.append(_MoreCommandInfoButton(self.pagination.more_details))
            container.add_item(discord.ui.Separator())
            container.add_item(discord.ui.ActionRow(*controls))
