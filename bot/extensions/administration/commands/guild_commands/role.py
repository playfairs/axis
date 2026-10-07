import asyncio

import discord
from rapidfuzz import process

from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands
from bot.core.client.help import help_command
from bot.errors.handlers import roles as role_error_handler
from bot.extensions.information.commands.guild_commands.role_info import (
    role_info as role_info_command,
)


class RoleMessageView(discord.ui.LayoutView):
    def __init__(self, message: str) -> None:
        super().__init__()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"> {message}"),
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )


class RoleConfirmationControls(discord.ui.ActionRow):
    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = self.view
        if not isinstance(view, DangerousRoleConfirmationView):
            raise RuntimeError("Role confirmation controls are not attached correctly.")
        button.disabled = True
        await view.confirm(interaction)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.secondary)
    async def deny(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = self.view
        if not isinstance(view, DangerousRoleConfirmationView):
            raise RuntimeError("Role confirmation controls are not attached correctly.")
        button.disabled = True
        await view.deny(interaction)


class DangerousRoleConfirmationView(discord.ui.LayoutView):
    def __init__(
        self,
        ctx: commands.Context,
        member: discord.Member,
        target: discord.Role,
    ) -> None:
        super().__init__(timeout=63)
        self.ctx = ctx
        self.member = member
        self.target = target
        self.response_message: discord.Message | None = None
        self.message = discord.ui.TextDisplay("")
        self.timer = discord.ui.TextDisplay(
            "Confirm and Deny buttons will appear in 3 second(s)."
        )
        self.controls = RoleConfirmationControls()
        self.container = discord.ui.Container(
            self.message,
            discord.ui.Separator(),
            self.timer,
            accent_color=DEFAULT_CONTAINER_COLOR,
        )
        self.add_item(self.container)
        dangerous_permissions = _dangerous_permissions(target)
        permission_list = ", ".join(dangerous_permissions)
        self.confirmation_text = (
            f"**Are you sure this is the role you meant?**\n"
            f"Fuzzy matching selected {target.mention} for {member.mention}.\n"
            f"This role has powerful permissions: {permission_list}.\n"
            "Review the role and permissions carefully before confirming."
        )
        self.message.content = self.confirmation_text

    def show_confirmation(self) -> None:
        self.container.remove_item(self.timer)
        self.container.add_item(self.controls)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(
                "Only the person who ran this command can confirm it.",
                ephemeral=True,
            )
            return False
        return True

    async def confirm(self, interaction: discord.Interaction) -> None:
        self._disable_controls()
        self.message.content = (
            f"Confirmed. Giving {self.target.mention} to {self.member.mention}."
        )
        await interaction.response.edit_message(
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        await _edit_member_role(
            self.ctx,
            self.member,
            self.target,
            give=True,
        )

    async def deny(self, interaction: discord.Interaction) -> None:
        self._disable_controls()
        self.message.content = "Role assignment cancelled, be more specific next time."
        await interaction.response.edit_message(
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def on_timeout(self) -> None:
        self._disable_controls()
        self.message.content = "Role assignment confirmation expired."
        if self.response_message is not None:
            await self.response_message.edit(
                view=self,
                allowed_mentions=discord.AllowedMentions.none(),
            )

    def _disable_controls(self) -> None:
        for item in self.controls.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class FuzzyRoleConverter(commands.RoleConverter):
    async def resolve(
        self,
        ctx: commands.Context,
        argument: str,
    ) -> tuple[discord.Role, bool]:
        try:
            return await super().convert(ctx, argument), False
        except commands.RoleNotFound:
            if ctx.guild is None:
                raise

        if len(argument.strip()) == 1 and argument.strip().isalpha():
            raise role_error_handler.RoleCommandError(
                "Please be more specific. Fuzzy role matching with a single letter "
                "isn't effective."
            )

        role_names = [role.name for role in ctx.guild.roles]
        closest_matches = process.extract(argument, role_names, limit=1)
        if closest_matches:
            _, score, index = closest_matches[0]
            if score > 60:
                return ctx.guild.roles[index], True

        raise commands.RoleNotFound(argument)

    async def convert(self, ctx: commands.Context, argument: str) -> discord.Role:
        role, _ = await self.resolve(ctx, argument)
        return role


DANGEROUS_PERMISSION_FLAGS = frozenset(
    {
        "administrator",
        "ban_members",
        "deafen_members",
        "kick_members",
        "manage_messages",
        "manage_nicknames",
        "moderate_members",
        "move_members",
        "mute_members",
        "mention_everyone",
        "priority_speaker",
        "view_audit_log",
    }
)

ROLE_COLOR_NAMES = {
    "blue": discord.Colour.blue,
    "blurple": discord.Colour.blurple,
    "brand_green": discord.Colour.brand_green,
    "brand_red": discord.Colour.brand_red,
    "dark_blue": discord.Colour.dark_blue,
    "dark_gold": discord.Colour.dark_gold,
    "dark_green": discord.Colour.dark_green,
    "dark_magenta": discord.Colour.dark_magenta,
    "dark_orange": discord.Colour.dark_orange,
    "dark_purple": discord.Colour.dark_purple,
    "dark_red": discord.Colour.dark_red,
    "dark_teal": discord.Colour.dark_teal,
    "fuchsia": discord.Colour.fuchsia,
    "gold": discord.Colour.gold,
    "green": discord.Colour.green,
    "greyple": discord.Colour.greyple,
    "magenta": discord.Colour.magenta,
    "og_blurple": discord.Colour.og_blurple,
    "orange": discord.Colour.orange,
    "pink": discord.Colour.pink,
    "purple": discord.Colour.purple,
    "red": discord.Colour.red,
    "teal": discord.Colour.teal,
    "yellow": discord.Colour.yellow,
}


def _dangerous_permissions(role: discord.Role) -> list[str]:
    permissions = role.permissions
    flags = discord.Permissions.VALID_FLAGS
    labels = {"manage_guild": "Manage Server"}
    return [
        labels.get(flag, flag.replace("_", " ").title())
        for flag in flags
        if (flag.startswith("manage_") or flag in DANGEROUS_PERMISSION_FLAGS)
        and getattr(permissions, flag)
    ]


def _parse_role_color(value: str) -> discord.Colour:
    normalized = value.strip().casefold()
    named_color = ROLE_COLOR_NAMES.get(normalized)
    if named_color is not None:
        return named_color()
    if len(normalized) in (3, 6) and all(
        character in "0123456789abcdef" for character in normalized
    ):
        normalized = f"#{normalized}"
    return discord.Colour.from_str(normalized)


async def _resolve_role_input(
    ctx: commands.Context,
    argument: str,
) -> tuple[discord.Role, bool]:
    return await FuzzyRoleConverter().resolve(ctx, argument)


async def _confirm_dangerous_fuzzy_give(
    ctx: commands.Context,
    member: discord.Member,
    target: discord.Role,
    *,
    fuzzy_match: bool,
) -> bool:
    if not fuzzy_match or member.guild_permissions.administrator:
        return False
    dangerous_permissions = _dangerous_permissions(target)
    if not dangerous_permissions:
        return False
    view = DangerousRoleConfirmationView(ctx, member, target)
    view.response_message = await ctx.send(
        view=view,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    for countdown in (2, 1):
        await asyncio.sleep(1)
        view.timer.content = (
            f"Confirm and Deny buttons will appear in {countdown} "
            "second(s)."
        )
        await view.response_message.edit(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    await asyncio.sleep(1)
    view.show_confirmation()
    await view.response_message.edit(
        view=view,
        allowed_mentions=discord.AllowedMentions.none(),
    )
    return True


def _managed_or_default(role: discord.Role) -> bool:
    return role.is_default() or role.managed


async def _check_actor_role_hierarchy(
    ctx: commands.Context,
    target: discord.Role,
) -> bool:
    if ctx.guild is None:
        await _send_message(ctx, "This command can only be used in a server.")
        return False
    if not isinstance(ctx.author, discord.Member):
        await _send_message(ctx, "Your server permissions couldn't be verified.")
        return False
    if ctx.author.id != ctx.guild.owner_id and target >= ctx.author.top_role:
        await _send_message(
            ctx,
            "You can't manage a role that is equal to or higher than your "
            "highest role.",
        )
        return False
    return True


async def _send_message(ctx: commands.Context, message: str) -> None:
    await ctx.send(
        view=RoleMessageView(message),
        allowed_mentions=discord.AllowedMentions.none(),
    )


def _missing_role_permissions(
    member: discord.Member,
    target: discord.Role,
) -> list[str]:
    missing: list[str] = []
    if not member.guild_permissions.manage_roles:
        missing.append("Manage Roles")
    if target.permissions.administrator and not member.guild_permissions.administrator:
        missing.append("Administrator")
    return missing


async def _handle_role_error(
    ctx: commands.Context,
    error: commands.CommandError,
) -> None:
    handled = await role_error_handler.handle_role_error(ctx, error)
    if not handled:
        raise RuntimeError(
            "The role error handler did not handle a role command error."
        )


async def _check_role_editable(
    ctx: commands.Context,
    target: discord.Role,
) -> bool:
    if ctx.guild is None:
        await _send_message(ctx, "This command can only be used in a server.")
        return False
    if target.guild != ctx.guild:
        await _send_message(ctx, "That role isn't in this server.")
        return False
    if _managed_or_default(target):
        await _send_message(
            ctx, "That role can't be changed because it is managed or @everyone."
        )
        return False
    if not await _check_actor_role_hierarchy(ctx, target):
        return False

    bot_member = ctx.guild.me
    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        await _send_message(
            ctx,
            "The bot is missing the required permissions to do that: `Manage Roles`",
        )
        return False
    if target >= bot_member.top_role:
        await _handle_role_error(ctx, role_error_handler.BotRoleHierarchyError())
        return False
    return True


async def _assign_role_to_matching_members(
    ctx: commands.Context,
    target: discord.Role,
    *,
    bots: bool,
) -> None:
    guild = ctx.guild
    if guild is None:
        await _send_message(ctx, "This command can only be used in a server.")
        return
    if not await _check_role_editable(ctx, target):
        return
    if not isinstance(ctx.author, discord.Member):
        await _send_message(ctx, "Your server permissions couldn't be verified.")
        return
    missing_permissions = _missing_role_permissions(ctx.author, target)
    if missing_permissions:
        missing = ", ".join(missing_permissions)
        await _send_message(
            ctx,
            f"You are missing the required permissions to do that: `{missing}`",
        )
        return

    assigned = 0
    async with ctx.typing():
        async for member in guild.fetch_members(limit=None):
            if member.bot != bots or target in member.roles:
                continue
            await member.add_roles(
                target,
                reason=f"Role given by {ctx.author}.",
            )
            assigned += 1

    member_type = "bot" if bots else "human"
    await _send_message(
        ctx,
        f"Added {target.mention} to {assigned} {member_type} "
        f"{'member' if assigned == 1 else 'members'}.",
    )


@commands.group(
    name="role",
    aliases=["r"],
    invoke_without_command=True,
    description="Manage server roles.",
)
async def role(
    ctx: commands.Context,
    member: discord.Member | None = None,
    *,
    role_input: str | None = None,
) -> None:
    if member is not None and role_input is not None:
        try:
            target, fuzzy_match = await _resolve_role_input(ctx, role_input)
        except role_error_handler.RoleCommandError as error:
            await _send_message(ctx, str(error))
            return
        give = target not in member.roles
        if give and await _confirm_dangerous_fuzzy_give(
            ctx,
            member,
            target,
            fuzzy_match=fuzzy_match,
        ):
            return
        await _edit_member_role(
            ctx,
            member,
            target,
            give=give,
        )
        return
    await ctx.invoke(help_command, command_name="role")


@role.command(
    name="create",
    aliases=["c", "new"],
    description="Create a role with optional permissions and color.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def role_create(
    ctx: commands.Context,
    *,
    name: str = "new-role",
) -> None:
    if ctx.guild is None:
        await _send_message(ctx, "This command can only be used in a server.")
        return
    name = name.strip()
    permissions_value = 0
    color: discord.Colour | None = None
    options: dict[str, str] = {}
    while True:
        name_parts = name.rsplit(maxsplit=1)
        if len(name_parts) != 2:
            break
        option_name, separator, option_value = name_parts[1].partition("=")
        option_name = option_name.casefold()
        if not separator or option_name not in {"perms", "color"}:
            break
        if option_name in options:
            await _send_message(ctx, f"Specify `{option_name}=` only once.")
            return
        options[option_name] = option_value
        name = name_parts[0]

    if "perms" in options:
        value = options["perms"]
        if not value.isdecimal():
            await _send_message(ctx, "Permission values must be a non-negative integer.")
            return
        permissions_value = int(value)
        if permissions_value > (1 << 53) - 1:
            await _send_message(
                ctx, "Permission values must be between 0 and 9007199254740991."
            )
            return
    if "color" in options:
        try:
            color = _parse_role_color(options["color"])
        except (TypeError, ValueError):
            await _send_message(
                ctx,
                "Use a hex color such as `C4A7E7`, `#C4A7E7`, or `CAE`, "
                "or a named color such as `Purple`.",
            )
            return

    if not isinstance(ctx.author, discord.Member):
        await _send_message(ctx, "Your server permissions couldn't be verified.")
        return
    permissions = discord.Permissions(permissions_value)
    if not permissions.is_subset(ctx.author.guild_permissions):
        await _send_message(ctx, "You can only create roles with permissions you have.")
        return

    if not name or len(name) > 100:
        await _send_message(ctx, "Role names must be between 1 and 100 characters.")
        return

    created = await ctx.guild.create_role(
        name=name,
        permissions=permissions,
        color=color,
        reason=f"Created by {ctx.author}.",
    )
    await _send_message(ctx, f"Created {created.mention}.")


@role.command(name="delete", aliases=["rm"], description="Delete a server role.")
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def role_delete(
    ctx: commands.Context,
    target: discord.Role = commands.parameter(  # noqa: B008
        converter=FuzzyRoleConverter
    ),
) -> None:
    if ctx.guild is None:
        await _send_message(ctx, "This command can only be used in a server.")
        return
    if target.guild != ctx.guild:
        await _send_message(ctx, "That role isn't in this server.")
        return
    if _managed_or_default(target):
        await _send_message(
            ctx, "That role can't be deleted because it is managed or @everyone."
        )
        return
    if not await _check_actor_role_hierarchy(ctx, target):
        return

    role_name = target.name
    await target.delete(reason=f"Deleted by {ctx.author}.")
    await _send_message(ctx, f"Deleted **{role_name}**.")


async def _edit_member_role(
    ctx: commands.Context,
    member: discord.Member,
    target: discord.Role,
    *,
    give: bool,
) -> None:
    if ctx.guild is None:
        await _send_message(ctx, "This command can only be used in a server.")
        return
    if target.guild != ctx.guild or member.guild != ctx.guild:
        await _send_message(ctx, "The member and role must be from this server.")
        return
    bot_member = ctx.guild.me
    if not isinstance(ctx.author, discord.Member):
        await _send_message(ctx, "Your server permissions couldn't be verified.")
        return

    missing_permissions = _missing_role_permissions(ctx.author, target)
    if missing_permissions:
        missing = ", ".join(missing_permissions)
        await _send_message(
            ctx,
            f"You are missing the required permissions to do that: `{missing}`",
        )
        return

    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        await _send_message(
            ctx,
            "The bot is missing the required permissions to do that: `Manage Roles`",
        )
        return
    if target.is_default():
        await _send_message(ctx, "The @everyone role can't be assigned or removed.")
        return
    if target.managed:
        await _handle_role_error(ctx, role_error_handler.ManagedRoleError())
        return
    if not await _check_actor_role_hierarchy(ctx, target):
        return
    if target >= bot_member.top_role:
        await _handle_role_error(ctx, role_error_handler.BotRoleHierarchyError())
        return

    if give:
        await member.add_roles(
            target,
            reason=f"Role given by {ctx.author}.",
        )
    else:
        await member.remove_roles(
            target,
            reason=f"Role removed by {ctx.author}.",
        )

    verb = "Gave" if give else "Removed"
    await _send_message(
        ctx, f"{verb} {target.mention} {'to' if give else 'from'} {member.mention}."
    )


@role.command(
    name="give",
    aliases=("add", "grant"),
    description="Give a role to a member.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def role_give(
    ctx: commands.Context,
    member: discord.Member,
    *,
    role_input: str,
) -> None:
    try:
        target, fuzzy_match = await _resolve_role_input(ctx, role_input)
    except role_error_handler.RoleCommandError as error:
        await _send_message(ctx, str(error))
        return
    if await _confirm_dangerous_fuzzy_give(
        ctx,
        member,
        target,
        fuzzy_match=fuzzy_match,
    ):
        return
    await _edit_member_role(ctx, member, target, give=True)


@role.command(
    name="remove",
    aliases=("revoke",),
    description="Remove a role from a member.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def role_remove(
    ctx: commands.Context,
    member: discord.Member,
    target: discord.Role = commands.parameter(  # noqa: B008
        converter=FuzzyRoleConverter
    ),
) -> None:
    await _edit_member_role(ctx, member, target, give=False)


@role.command(
    name="rename",
    aliases=["name"],
    description="Rename a server role.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def role_rename(
    ctx: commands.Context,
    target: discord.Role = commands.parameter(  # noqa: B008
        converter=FuzzyRoleConverter
    ),
    *,
    name: str,
) -> None:
    if ctx.guild is None:
        await _send_message(ctx, "This command can only be used in a server.")
        return
    if target.guild != ctx.guild:
        await _send_message(ctx, "That role isn't in this server.")
        return
    if _managed_or_default(target):
        await _send_message(
            ctx, "That role can't be renamed because it is managed or @everyone."
        )
        return
    if not await _check_actor_role_hierarchy(ctx, target):
        return

    name = name.strip()
    if not name or len(name) > 100:
        await _send_message(ctx, "Role names must be between 1 and 100 characters.")
        return
    old_name = target.name
    updated = await target.edit(
        name=name,
        reason=f"Renamed by {ctx.author}.",
    )
    await _send_message(ctx, f"Renamed **{old_name}** to **{updated.name}**.")


@role.command(
    name="color",
    aliases=("colour",),
    description="Change a role's color.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def role_color(
    ctx: commands.Context,
    target: discord.Role = commands.parameter(  # noqa: B008
        converter=FuzzyRoleConverter
    ),
    *,
    color: str,
) -> None:
    if ctx.guild is None:
        await _send_message(ctx, "This command can only be used in a server.")
        return
    if target.guild != ctx.guild:
        await _send_message(ctx, "That role isn't in this server.")
        return
    if _managed_or_default(target):
        await _send_message(ctx, "That role's color can't be changed.")
        return
    if not await _check_actor_role_hierarchy(ctx, target):
        return
    try:
        parsed_color = _parse_role_color(color)
    except (TypeError, ValueError):
        await _send_message(
            ctx,
            "Use a hex color such as `C4A7E7`, `#C4A7E7`, or `CAE`, "
            "or a named color such as `Purple`.",
        )
        return

    updated = await target.edit(
        color=parsed_color,
        reason=f"Color changed by {ctx.author}.",
    )
    await _send_message(
        ctx, f"Changed **{updated.name}**'s color to `#{updated.color.value:06X}`."
    )


@role.command(
    name="hoist",
    description="Toggle whether a role is displayed separately in the member list.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def role_hoist(
    ctx: commands.Context,
    target: discord.Role = commands.parameter(  # noqa: B008
        converter=FuzzyRoleConverter
    ),
) -> None:
    if not await _check_role_editable(ctx, target):
        return
    hoist = not target.hoist
    updated = await target.edit(
        hoist=hoist,
        reason=f"Hoist visibility changed by {ctx.author}.",
    )
    await _send_message(
        ctx,
        f"{'Displayed' if updated.hoist else 'No longer displaying'} "
        f"**{updated.name}** separately in the member list.",
    )


@role.command(
    name="human",
    description="Add this role to every non-bot member who does not already have it.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def role_human(
    ctx: commands.Context,
    target: discord.Role = commands.parameter(  # noqa: B008
        converter=FuzzyRoleConverter
    ),
) -> None:
    await _assign_role_to_matching_members(ctx, target, bots=False)


@role.command(
    name="bot",
    description="Add this role to every bot member who does not already have it.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def role_bot(
    ctx: commands.Context,
    target: discord.Role = commands.parameter(  # noqa: B008
        converter=FuzzyRoleConverter
    ),
) -> None:
    await _assign_role_to_matching_members(ctx, target, bots=True)


@role.command(
    name="info",
    aliases=("information",),
    description="Show information about a specific role.",
)
@commands.guild_only()
async def role_info(
    ctx: commands.Context,
    target: discord.Role = commands.parameter(  # noqa: B008
        converter=FuzzyRoleConverter
    ),
) -> None:
    if ctx.guild is None:
        await _send_message(ctx, "This command can only be used in a server.")
        return
    if target.guild != ctx.guild:
        await _send_message(ctx, "That role isn't in this server.")
        return
    await ctx.invoke(role_info_command, role=target)
