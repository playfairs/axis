from collections.abc import Sequence

from bot.base.imports import DEFAULT_CONTAINER_COLOR, app_commands, commands, discord


class MissingPermissionsView(discord.ui.LayoutView):
    def __init__(self, message: str) -> None:
        super().__init__()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(message),
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )


def _permission_names(permissions: Sequence[str]) -> str:
    return ", ".join(
        permission.replace("_", " ").title() for permission in permissions
    )


def _is_user_missing_permissions(error: BaseException) -> bool:
    return isinstance(
        error,
        (
            commands.MissingPermissions,
            app_commands.MissingPermissions,
        ),
    )


def _is_bot_missing_permissions(error: BaseException) -> bool:
    return isinstance(
        error,
        (
            commands.BotMissingPermissions,
            app_commands.BotMissingPermissions,
        ),
    )


def _unwrap_command_error(error: BaseException) -> BaseException:
    while isinstance(
        error,
        (
            commands.HybridCommandError,
            commands.CommandInvokeError,
        ),
    ):
        error = error.original
    return error


async def send_missing_permissions(
    ctx: commands.Context,
    permissions: Sequence[str],
) -> None:
    message = (
        f"> {ctx.author.mention}, You are **missing** permission: "
        f"{_permission_names(permissions)}"
    )
    await ctx.send(
        view=MissingPermissionsView(message),
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def send_bot_missing_permissions(
    ctx: commands.Context,
    permissions: Sequence[str],
) -> None:
    message = f"> The bot is **missing** permission: {_permission_names(permissions)}"
    await ctx.send(
        view=MissingPermissionsView(message),
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def handle_missing_permissions_command_error(
    ctx: commands.Context,
    error: commands.CommandError,
) -> bool:
    cause = _unwrap_command_error(error)
    if _is_user_missing_permissions(cause):
        await send_missing_permissions(ctx, cause.missing_permissions)
        return True
    if _is_bot_missing_permissions(cause):
        await send_bot_missing_permissions(ctx, cause.missing_permissions)
        return True
    return False


async def handle_missing_permissions_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> bool:
    if _is_user_missing_permissions(error):
        message = (
            f"> {interaction.user.mention}, You are **missing** permission: "
            f"{_permission_names(error.missing_permissions)}"
        )
    elif _is_bot_missing_permissions(error):
        message = (
            f"> The bot is **missing** permission: "
            f"{_permission_names(error.missing_permissions)}"
        )
    else:
        return False

    view = MissingPermissionsView(message)
    if interaction.response.is_done():
        await interaction.followup.send(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    else:
        await interaction.response.send_message(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    return True