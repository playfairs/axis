from __future__ import annotations

import re

from discord import app_commands

from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord
from bot.definitions.permissions import PERMISSIONS

ROLE_MENTION = re.compile(r"<@&(\d+)>")
MEMBER_MENTION = re.compile(r"<@!?(\d+)>")


def _format_permissions(permissions: discord.Permissions) -> str:
    if permissions.administrator:
        return "Administrator"

    enabled = [
        name.replace("_", " ").title()
        for name, value in permissions
        if value
    ]
    return ", ".join(f"`{name}`" for name in enabled) or "None"


def _format_channel_permission_grants(
    base_permissions: discord.Permissions,
    overwrite: discord.PermissionOverwrite,
) -> str | None:
    if base_permissions.administrator:
        return None

    labels = {"read_messages": "View Channel"}
    granted = sorted(
        {
            labels.get(name, name.replace("_", " ").title())
            for name in discord.PermissionOverwrite.VALID_NAMES
            if getattr(overwrite, name) is True
        }
    )
    if not granted:
        return None

    return ", ".join(f"`{name}`" for name in granted)


class PermissionsView(discord.ui.LayoutView):
    def __init__(
        self,
        title: str,
        server_label: str,
        server_permissions: discord.Permissions,
        channel: discord.abc.GuildChannel | None,
        channel_overwrite: discord.PermissionOverwrite | None,
    ) -> None:
        super().__init__()
        content = [
            discord.ui.TextDisplay(f"## {title}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                f"**{server_label}:** {_format_permissions(server_permissions)}"
            ),
        ]
        channel_grants = (
            _format_channel_permission_grants(
                server_permissions,
                channel_overwrite,
            )
            if channel_overwrite is not None
            else None
        )
        if channel is not None and channel_grants is not None:
            content.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.TextDisplay(
                        f"**Effective in {channel.mention}:** "
                        f"{channel_grants}"
                    ),
                )
            )
        self.add_item(
            discord.ui.Container(
                *content,
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )


async def _send_message(ctx: commands.Context, message: str) -> None:
    chunks: list[str] = []
    current = ""
    for line in message.splitlines() or [""]:
        while len(line) > 1900:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:1900])
            line = line[1900:]
        if current and len(current) + len(line) + 1 > 1900:
            chunks.append(current)
            current = ""
        current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)

    for chunk in chunks:
        await ctx.send(
            chunk,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def _resolve_target(
    ctx: commands.Context,
    argument: str,
) -> discord.Role | discord.Member | None:
    guild = ctx.guild
    if guild is None:
        return None

    value = argument.strip()
    role_mention = ROLE_MENTION.fullmatch(value)
    if role_mention is not None:
        return guild.get_role(int(role_mention.group(1)))

    member_mention = MEMBER_MENTION.fullmatch(value)
    if member_mention is not None:
        member_id = int(member_mention.group(1))
        member = guild.get_member(member_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(member_id)
        except discord.NotFound:
            return None

    if value.isdecimal():
        target_id = int(value)
        role = guild.get_role(target_id)
        if role is not None:
            return role
        member = guild.get_member(target_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(target_id)
        except discord.NotFound:
            return None

    normalized = value.casefold()
    matching_roles = [
        role for role in guild.roles if role.name.casefold() == normalized
    ]
    matching_members = [
        member
        for member in guild.members
        if normalized in {
            member.name.casefold(),
            member.display_name.casefold(),
            (member.global_name or "").casefold(),
        }
    ]
    matches: list[discord.Role | discord.Member] = [
        *matching_roles,
        *matching_members,
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def _permission_input_candidates() -> list[tuple[str, list[str]]]:
    candidates = [
        (name, [name])
        for name in discord.Permissions.VALID_FLAGS
    ]
    for alias, permissions in PERMISSIONS.ALIASES.items():
        permission_names = [permissions] if isinstance(permissions, str) else permissions
        candidates.append((alias, list(permission_names)))

    spellings: dict[str, list[str]] = {}
    for name, permission_names in candidates:
        for spelling in {name.casefold(), name.casefold().replace("_", " ")}:
            spellings[spelling] = [permission.casefold() for permission in permission_names]
    return sorted(spellings.items(), key=lambda item: len(item[0]), reverse=True)


def _split_target_and_permission(value: str) -> tuple[str, list[str]] | None:
    value = value.strip()
    for spelling, permission_names in _permission_input_candidates():
        suffix = f" {spelling}"
        if value.casefold().endswith(suffix):
            target = value[: -len(suffix)].strip()
            if target:
                return target, permission_names
    return None


def _permission_labels(permissions: list[str]) -> str:
    return ", ".join(
        f"`{permission.replace('_', ' ').title()}`"
        for permission in permissions
    )


def _current_channel(
    ctx: commands.Context,
) -> discord.abc.GuildChannel | None:
    if isinstance(ctx.channel, discord.abc.GuildChannel):
        return ctx.channel
    return None


@commands.hybrid_group(
    name="permissions",
    aliases=["perms"],
    invoke_without_command=True,
    description="View and manage server and channel permissions.",
)
@app_commands.guild_only()
@commands.guild_only()
@app_commands.describe(
    target_input="A user's or role's mention, ID, or exact name.",
)
async def permissions(
    ctx: commands.Context,
    *,
    target_input: str | None = None,
) -> None:
    if ctx.guild is None:
        await _send_message(ctx, "This command can only be used in a server.")
        return

    target: discord.Role | discord.Member | None
    if target_input is None:
        if not isinstance(ctx.author, discord.Member):
            await _send_message(ctx, "Your server permissions couldn't be verified.")
            return
        target = ctx.author
    else:
        target = await _resolve_target(ctx, target_input)
        if target is None:
            await _send_message(
                ctx,
                "I couldn't find one unambiguous user or role by that name. "
                "Try its mention or ID instead.",
            )
            return

    channel = _current_channel(ctx)
    if isinstance(target, discord.Member):
        title = f"Permissions for {target.mention}"
        target_permissions = target.guild_permissions
        permission_label = "Server"
    else:
        title = f"Permissions for {discord.utils.escape_markdown(target.name)}"
        target_permissions = target.permissions
        permission_label = "Role"

    channel_overwrite = (
        channel.overwrites_for(target)
        if channel is not None and isinstance(target, discord.Member)
        else None
    )
    await ctx.send(
        view=PermissionsView(
            title,
            permission_label,
            target_permissions,
            channel,
            channel_overwrite,
        ),
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def _change_permission(
    ctx: commands.Context,
    target_input: str,
    permission_names: list[str],
    *,
    grant: bool,
) -> None:
    guild = ctx.guild
    if guild is None:
        await _send_message(ctx, "This command can only be used in a server.")
        return

    target = await _resolve_target(ctx, target_input)
    if target is None:
        await _send_message(
            ctx,
            "I couldn't find one unambiguous user or role by that name. "
            "Try its mention or ID instead.",
        )
        return

    if isinstance(target, discord.Role):
        await _change_role_permission(ctx, target, permission_names, grant=grant)
    else:
        await _change_member_permission(ctx, target, permission_names, grant=grant)


async def _change_role_permission(
    ctx: commands.Context,
    target: discord.Role,
    permissions: list[str],
    *,
    grant: bool,
) -> None:
    guild = ctx.guild
    if guild is None:
        await _send_message(ctx, "This command can only be used in a server.")
        return
    invalid_permissions = set(permissions) - set(discord.Permissions.VALID_FLAGS)
    if invalid_permissions:
        await _send_message(
            ctx,
            f"These aren't valid Discord role permissions: "
            f"{_permission_labels(sorted(invalid_permissions))}.",
        )
        return
    if target.is_default() or target.managed:
        await _send_message(
            ctx,
            "The @everyone role and managed roles can't be changed this way.",
        )
        return
    if not isinstance(ctx.author, discord.Member):
        await _send_message(ctx, "Your server permissions couldn't be verified.")
        return
    if ctx.author.id != guild.owner_id and target >= ctx.author.top_role:
        await _send_message(
            ctx,
            "You can't manage a role that is equal to or higher than your "
            "highest role.",
        )
        return

    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        await _send_message(ctx, "I need the Manage Roles permission to do that.")
        return
    if target >= bot_member.top_role:
        await _send_message(
            ctx,
            "My highest role must be above the role you want to change.",
        )
        return

    permissions_value = discord.Permissions(target.permissions.value)
    changed_permissions = [
        permission
        for permission in permissions
        if getattr(permissions_value, permission) != grant
    ]
    if not changed_permissions:
        state = "already has" if grant else "doesn't have"
        await _send_message(
            ctx,
            f"{target.mention} {state} {_permission_labels(permissions)}.",
        )
        return

    for permission in changed_permissions:
        setattr(permissions_value, permission, grant)
    await target.edit(
        permissions=permissions_value,
        reason=(
            f"{'Granted' if grant else 'Revoked'} "
            f"{', '.join(changed_permissions)} by {ctx.author}."
        ),
    )
    verb = "Granted" if grant else "Revoked"
    await _send_message(
        ctx,
        f"{verb} {_permission_labels(changed_permissions)} for {target.mention}.",
    )


async def _change_member_permission(
    ctx: commands.Context,
    target: discord.Member,
    permissions: list[str],
    *,
    grant: bool,
) -> None:
    invalid_permissions = set(permissions) - discord.PermissionOverwrite.VALID_NAMES
    if invalid_permissions:
        await _send_message(
            ctx,
            "That permission can't be set for one user in a channel. "
            "Unsupported channel permissions: "
            f"{_permission_labels(sorted(invalid_permissions))}.",
        )
        return
    if not isinstance(ctx.author, discord.Member):
        await _send_message(ctx, "Your server permissions couldn't be verified.")
        return
    if not (
        ctx.author.guild_permissions.manage_roles
        or ctx.author.guild_permissions.administrator
    ):
        await _send_message(ctx, "You need Manage Roles to change channel permissions.")
        return

    channel = _current_channel(ctx)
    if channel is None:
        await _send_message(
            ctx,
            "Run this command in a regular server channel; Discord doesn't "
            "support permission overwrites on threads.",
        )
        return

    bot_member = ctx.guild.me if ctx.guild is not None else None
    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        await _send_message(ctx, "I need the Manage Roles permission to do that.")
        return

    overwrite = channel.overwrites_for(target)
    changed_permissions = [
        permission
        for permission in permissions
        if getattr(overwrite, permission) is not grant
    ]
    if not changed_permissions:
        state = "already has" if grant else "is already denied"
        await _send_message(
            ctx,
            f"{target.mention} {state} {_permission_labels(permissions)} "
            f"in {channel.mention}.",
        )
        return

    for permission in changed_permissions:
        setattr(overwrite, permission, grant)
    await channel.set_permissions(
        target,
        overwrite=overwrite,
        reason=(
            f"{'Granted' if grant else 'Revoked'} "
            f"{', '.join(changed_permissions)} for {target} "
            f"in #{channel.name} by {ctx.author}."
        ),
    )
    verb = "Granted" if grant else "Revoked"
    await _send_message(
        ctx,
        f"{verb} {_permission_labels(changed_permissions)} for "
        f"{target.mention} in {channel.mention}. "
        "This permission change applies only to that channel.",
    )


@permissions.command(
    name="grant",
    description="Grant a role or user a permission.",
)
@app_commands.guild_only()
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    target_and_permission=(
        "A user or role mention/ID/name followed by a permission name or alias."
    ),
)
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def permissions_grant(
    ctx: commands.Context,
    *,
    target_and_permission: str,
) -> None:
    parsed = _split_target_and_permission(target_and_permission)
    if parsed is None:
        await _send_message(
            ctx,
            "Include a target and permission, for example "
            "`permissions grant @Helpers attach files` or "
            "`permissions grant @Helpers pic`.",
        )
        return
    await _change_permission(ctx, *parsed, grant=True)


@permissions.command(
    name="revoke",
    description="Revoke a role or user permission.",
)
@app_commands.guild_only()
@app_commands.default_permissions(manage_roles=True)
@app_commands.describe(
    target_and_permission=(
        "A user or role mention/ID/name followed by a permission name or alias."
    ),
)
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def permissions_revoke(
    ctx: commands.Context,
    *,
    target_and_permission: str,
) -> None:
    parsed = _split_target_and_permission(target_and_permission)
    if parsed is None:
        await _send_message(
            ctx,
            "Include a target and permission, for example "
            "`permissions revoke @Helpers attach files` or "
            "`permissions revoke @Helpers pic`.",
        )
        return
    await _change_permission(ctx, *parsed, grant=False)