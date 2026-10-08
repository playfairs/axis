from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord


def format_moderation_result(
    action: str,
    target: discord.Member,
    reason: str | None,
    *,
    duration: str | None = None,
) -> str:
    content = f"> {action} {target.mention}"
    if duration is not None:
        content += f" for {duration}"
    if reason is not None:
        content += f" with reason: **{reason}**"
    return content


class ModerationResultView(discord.ui.LayoutView):
    def __init__(
        self,
        action: str,
        target: discord.Member,
        reason: str | None,
        *,
        duration: str | None = None,
    ) -> None:
        super().__init__()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    format_moderation_result(
                        action,
                        target,
                        reason,
                        duration=duration,
                    )
                ),
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )


class ModerationErrorView(discord.ui.LayoutView):
    def __init__(self, message: str) -> None:
        super().__init__()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"> {message}"),
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )


async def send_moderation_error(
    ctx: commands.Context,
    message: str,
) -> None:
    await ctx.send(
        view=ModerationErrorView(message),
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def send_moderation_result(
    ctx: commands.Context,
    action: str,
    target: discord.Member,
    reason: str | None,
    *,
    duration: str | None = None,
) -> None:
    await ctx.send(
        view=ModerationResultView(
            action,
            target,
            reason,
            duration=duration,
        ),
        allowed_mentions=discord.AllowedMentions.none(),
    )


def moderation_target_error(
    ctx: commands.Context,
    target: discord.Member,
) -> str | None:
    guild = ctx.guild
    if guild is None:
        return "This command can only be used in a server."
    if target.guild != guild:
        return "You can only take action on members of this server."
    if not isinstance(ctx.author, discord.Member):
        return "Your server role couldn't be verified."
    if target.id == ctx.author.id:
        return "You can't take action on yourself."
    if target.id == guild.owner_id:
        return "You can't take action on the server owner."

    bot_member = guild.me
    if bot_member is None:
        return "I couldn't verify my role in this server."
    if target.id == bot_member.id:
        return "I can't take action on myself."

    if ctx.author.id != guild.owner_id and target.top_role >= ctx.author.top_role:
        return "You can't take action on someone with the same or a higher role."

    if target.top_role >= bot_member.top_role:
        return "I can't take action on someone with the same or a higher top role than me."
    return None
