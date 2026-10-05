from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord, logger
from bot.core.client.help import help_command


class RoleMessageView(discord.ui.LayoutView):
    def __init__(self, message: str) -> None:
        super().__init__()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"> {message}"),
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )


async def send_role_message(ctx: commands.Context, message: str) -> None:
    await ctx.send(
        view=RoleMessageView(message),
        allowed_mentions=discord.AllowedMentions.none(),
    )


class RoleCommandError(commands.CommandError):
    """error messages for role commands"""


class ManagedRoleError(RoleCommandError):
    """Raised when a command attempts to manually change a Discord-managed role."""


class BotRoleHierarchyError(RoleCommandError):
    """Raised when the bot cannot manage a role above its highest role."""


def _is_role_command(ctx: commands.Context) -> bool:
    if ctx.command is None:
        return False
    root_name = ctx.command.qualified_name.partition(" ")[0].casefold()
    return root_name in {"role", "roleinfo", "ri"}


async def handle_role_error(
    ctx: commands.Context,
    error: commands.CommandError,
) -> bool:
    cause = error.original if isinstance(error, commands.CommandInvokeError) else error

    if isinstance(cause, ManagedRoleError):
        await send_role_message(
            ctx,
            "That role is managed by Discord (such as a bot, server boost, or "
            "subscription role) and can't be assigned or removed manually.",
        )
        return True
    if isinstance(cause, BotRoleHierarchyError):
        await send_role_message(
            ctx,
            "I can't assign or remove that role because it is higher than or equal "
            "to my highest role. Move my role above it and try again.",
        )
        return True
    if not _is_role_command(ctx):
        return False

    if isinstance(cause, RoleCommandError):
        await send_role_message(ctx, str(cause))
    elif isinstance(cause, commands.BotMissingPermissions):
        missing = ", ".join(
            _permission_name(permission) for permission in cause.missing_permissions
        )
        await send_role_message(
            ctx, f"The bot is missing the required permissions to do that: `{missing}`"
        )
    elif isinstance(cause, commands.MissingPermissions):
        missing = ", ".join(
            _permission_name(permission) for permission in cause.missing_permissions
        )
        await send_role_message(
            ctx, f"You are missing the required permissions to do that: `{missing}`"
        )
    elif isinstance(cause, commands.NoPrivateMessage):
        await send_role_message(ctx, "Role commands can only be used in a server.")
    elif isinstance(cause, commands.MissingRequiredArgument):
        await ctx.invoke(help_command, command_name="role")
    elif isinstance(cause, commands.MemberNotFound):
        await send_role_message(
            ctx, "Couldn't find that member. Mention them or use their ID."
        )
    elif isinstance(cause, commands.RoleNotFound):
        await send_role_message(
            ctx,
            "Couldn't find that role. Mention it, use its ID, or provide its exact name.",
        )
    elif isinstance(cause, commands.UserInputError):
        await ctx.invoke(help_command, command_name="role")
    elif isinstance(cause, discord.HTTPException):
        logger.warning(
            "Discord rejected role command %s in guild %s (HTTP %s).",
            ctx.command.qualified_name if ctx.command is not None else ctx.invoked_with,
            ctx.guild.id if ctx.guild is not None else "N/A",
            cause.status,
        )
        await send_role_message(
            ctx,
            "Discord couldn't complete that role change. Check the role hierarchy "
            "and make sure the bot's highest role is above the target role.",
        )
    else:
        logger.error(
            "Unhandled error in role command %s.",
            ctx.command.qualified_name if ctx.command is not None else ctx.invoked_with,
            exc_info=(type(cause), cause, cause.__traceback__),
        )
        await send_role_message(
            ctx, "Something went wrong while handling that role command."
        )

    return True


def _permission_name(permission: str) -> str:
    return permission.replace("_", " ").title()
