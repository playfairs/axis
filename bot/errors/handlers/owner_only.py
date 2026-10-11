from bot.base.imports import DEFAULT_CONTAINER_COLOR, app_commands, commands, discord


class OwnerOnlyCheckFailure(app_commands.CheckFailure):
    pass


async def application_owner_check(interaction: discord.Interaction) -> bool:
    if not await interaction.client.is_owner(interaction.user):
        raise OwnerOnlyCheckFailure
    return True


def owner_only_view() -> discord.ui.LayoutView:
    view = discord.ui.LayoutView()
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay("> This is an owner only command, sorry."),
            accent_color=DEFAULT_CONTAINER_COLOR,
        )
    )
    return view


def _is_owner_only_error(error: commands.CommandError) -> bool:
    current_error: BaseException = error
    while True:
        if isinstance(current_error, (commands.NotOwner, OwnerOnlyCheckFailure)):
            return True
        if isinstance(current_error, commands.HybridCommandError):
            current_error = current_error.original
            continue
        if isinstance(current_error, commands.CommandInvokeError):
            current_error = current_error.original
            continue
        return False


async def handle_owner_only_command_error(
    ctx: commands.Context,
    error: commands.CommandError,
) -> bool:
    if not _is_owner_only_error(error):
        return False

    await ctx.send(
        view=owner_only_view(),
        allowed_mentions=discord.AllowedMentions.none(),
    )
    return True


async def handle_owner_only_app_command_error(
    interaction: discord.Interaction,
    error: app_commands.AppCommandError,
) -> bool:
    if not isinstance(error, OwnerOnlyCheckFailure):
        return False

    view = owner_only_view()
    if interaction.response.is_done():
        await interaction.followup.send(
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    else:
        await interaction.response.send_message(
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    return True