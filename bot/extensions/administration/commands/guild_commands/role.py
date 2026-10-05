import asyncio
import os

import discord

from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, logger
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


class FuzzyRoleConverter(commands.RoleConverter):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Role:
        try:
            return await super().convert(ctx, argument)
        except commands.RoleNotFound:
            if ctx.guild is None:
                raise

        roles_by_name = {
            " ".join(role.name.casefold().split()): role for role in ctx.guild.roles
        }
        if not roles_by_name:
            raise commands.RoleNotFound(argument)

        try:
            process = await asyncio.create_subprocess_exec(
                "fzf",
                "--filter",
                argument,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={**os.environ, "FZF_DEFAULT_OPTS": ""},
            )
        except FileNotFoundError as error:
            raise role_error_handler.RoleCommandError(
                "Fuzzy role matching requires the `fzf` executable to be installed."
            ) from error

        stdout, stderr = await process.communicate(
            "\n".join(role.name for role in ctx.guild.roles).encode()
        )
        if process.returncode == 2:
            detail = stderr.decode(errors="replace").strip()
            logger.error("fzf failed while matching role %r: %s", argument, detail)
            raise role_error_handler.RoleCommandError(
                "Fuzzy role matching failed. Please use the exact role name or "
                "mention the role."
            )
        if process.returncode not in (0, 1):
            detail = stderr.decode(errors="replace").strip()
            logger.error(
                "fzf exited with status %s while matching role %r: %s",
                process.returncode,
                argument,
                detail,
            )
            raise role_error_handler.RoleCommandError(
                "Fuzzy role matching failed. Please try the role name again."
            )

        match = stdout.decode().splitlines()
        if not match:
            raise commands.RoleNotFound(argument)
        return roles_by_name[" ".join(match[0].casefold().split())]


def _managed_or_default(role: discord.Role) -> bool:
    return role.is_default() or role.managed


async def _check_actor_role_hierarchy(
    ctx: commands.Context,
    target: discord.Role,
) -> bool:
    if ctx.guild is None:
        await _send_error(ctx, "This command can only be used in a server.")
        return False
    if not isinstance(ctx.author, discord.Member):
        await _send_error(ctx, "Your server permissions couldn't be verified.")
        return False
    if ctx.author.id != ctx.guild.owner_id and target >= ctx.author.top_role:
        await _send_error(
            ctx,
            "You can't manage a role that is equal to or higher than your "
            "highest role.",
        )
        return False
    return True


async def _send_error(ctx: commands.Context, message: str) -> None:
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


@commands.group(
    name="role",
    aliases=["r"],
    invoke_without_command=True,
)
async def role(
    ctx: commands.Context,
    member: discord.Member | None = None,
    target: discord.Role | None = commands.parameter(  # noqa: B008
        converter=FuzzyRoleConverter,
        default=None,
    ),
) -> None:
    if member is not None and target is not None:
        await _edit_member_role(
            ctx,
            member,
            target,
            give=target not in member.roles,
        )
        return
    await ctx.invoke(help_command, command_name="role")


@role.command(name="create", aliases=["c", "new"])
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def role_create(
    ctx: commands.Context,
    *,
    name: str = "new-role",
) -> None:
    if ctx.guild is None:
        await _send_error(ctx, "This command can only be used in a server.")
        return
    name = name.strip()
    permissions_value = 0
    name_parts = name.rsplit(maxsplit=1)
    if len(name_parts) == 2 and name_parts[1].casefold().startswith("perms="):
        name, option = name_parts
        value = option.partition("=")[2]
        if not value.isdecimal():
            await _send_error(ctx, "Permission values must be a non-negative integer.")
            return
        permissions_value = int(value)
        if permissions_value > (1 << 53) - 1:
            await _send_error(
                ctx, "Permission values must be between 0 and 9007199254740991."
            )
            return

    if not isinstance(ctx.author, discord.Member):
        await _send_error(ctx, "Your server permissions couldn't be verified.")
        return
    permissions = discord.Permissions(permissions_value)
    if not permissions.is_subset(ctx.author.guild_permissions):
        await _send_error(ctx, "You can only create roles with permissions you have.")
        return

    if not name or len(name) > 100:
        await _send_error(ctx, "Role names must be between 1 and 100 characters.")
        return

    created = await ctx.guild.create_role(
        name=name,
        permissions=permissions,
        reason=f"Created by {ctx.author} via role command",
    )
    await _send_error(ctx, f"Created {created.mention}.")


@role.command(name="delete", aliases=["rm"])
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
        await _send_error(ctx, "This command can only be used in a server.")
        return
    if target.guild != ctx.guild:
        await _send_error(ctx, "That role isn't in this server.")
        return
    if _managed_or_default(target):
        await _send_error(
            ctx, "That role can't be deleted because it is managed or @everyone."
        )
        return
    if not await _check_actor_role_hierarchy(ctx, target):
        return

    role_name = target.name
    await target.delete(reason=f"Deleted by {ctx.author} via role command")
    await _send_error(ctx, f"Deleted **{role_name}**.")


async def _edit_member_role(
    ctx: commands.Context,
    member: discord.Member,
    target: discord.Role,
    *,
    give: bool,
) -> None:
    if ctx.guild is None:
        await _send_error(ctx, "This command can only be used in a server.")
        return
    if target.guild != ctx.guild or member.guild != ctx.guild:
        await _send_error(ctx, "The member and role must be from this server.")
        return
    bot_member = ctx.guild.me
    if not isinstance(ctx.author, discord.Member):
        await _send_error(ctx, "Your server permissions couldn't be verified.")
        return

    missing_permissions = _missing_role_permissions(ctx.author, target)
    if missing_permissions:
        missing = ", ".join(missing_permissions)
        await _send_error(
            ctx,
            f"You are missing the required permissions to do that: `{missing}`",
        )
        return

    if bot_member is None or not bot_member.guild_permissions.manage_roles:
        await _send_error(
            ctx,
            "The bot is missing the required permissions to do that: `Manage Roles`",
        )
        return
    if target.is_default():
        await _send_error(ctx, "The @everyone role can't be assigned or removed.")
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
            reason=f"Role given by {ctx.author} via role command",
        )
    else:
        await member.remove_roles(
            target,
            reason=f"Role removed by {ctx.author} via role command",
        )

    verb = "Gave" if give else "Removed"
    await _send_error(
        ctx, f"{verb} {target.mention} {'to' if give else 'from'} {member.mention}."
    )


@role.command(name="give", aliases=("add", "grant"))
@commands.guild_only()
@commands.has_guild_permissions(manage_roles=True)
@commands.bot_has_guild_permissions(manage_roles=True)
async def role_give(
    ctx: commands.Context,
    member: discord.Member,
    target: discord.Role = commands.parameter(  # noqa: B008
        converter=FuzzyRoleConverter
    ),
) -> None:
    await _edit_member_role(ctx, member, target, give=True)


@role.command(name="remove", aliases=("revoke",))
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


@role.command(name="rename", aliases=["name"])
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
        await _send_error(ctx, "This command can only be used in a server.")
        return
    if target.guild != ctx.guild:
        await _send_error(ctx, "That role isn't in this server.")
        return
    if _managed_or_default(target):
        await _send_error(
            ctx, "That role can't be renamed because it is managed or @everyone."
        )
        return
    if not await _check_actor_role_hierarchy(ctx, target):
        return

    name = name.strip()
    if not name or len(name) > 100:
        await _send_error(ctx, "Role names must be between 1 and 100 characters.")
        return
    old_name = target.name
    updated = await target.edit(
        name=name,
        reason=f"Renamed by {ctx.author} via role command",
    )
    await _send_error(ctx, f"Renamed **{old_name}** to **{updated.name}**.")


@role.command(name="color", aliases=("colour",))
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
        await _send_error(ctx, "This command can only be used in a server.")
        return
    if target.guild != ctx.guild:
        await _send_error(ctx, "That role isn't in this server.")
        return
    if _managed_or_default(target):
        await _send_error(ctx, "That role's color can't be changed.")
        return
    if not await _check_actor_role_hierarchy(ctx, target):
        return
    try:
        parsed_color = discord.Colour.from_str(color)
    except (TypeError, ValueError):
        await _send_error(ctx, "Use a color such as `#5865F2` or `0x5865F2`.")
        return

    updated = await target.edit(
        color=parsed_color,
        reason=f"Color changed by {ctx.author} via role command",
    )
    await _send_error(
        ctx, f"Changed **{updated.name}**'s color to `#{updated.color.value:06X}`."
    )


@role.command(name="info", aliases=("information",))
@commands.guild_only()
async def role_info(
    ctx: commands.Context,
    target: discord.Role = commands.parameter(  # noqa: B008
        converter=FuzzyRoleConverter
    ),
) -> None:
    if ctx.guild is None:
        await _send_error(ctx, "This command can only be used in a server.")
        return
    if target.guild != ctx.guild:
        await _send_error(ctx, "That role isn't in this server.")
        return
    await ctx.invoke(role_info_command, role=target)
