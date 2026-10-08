from bot.base.imports import commands, discord, logger
from bot.extensions.moderation._checks import (
    moderation_target_error,
    send_moderation_error,
    send_moderation_result,
)


@commands.command(
    name="ban",
    description="Ban a member from this server.",
)
@commands.guild_only()
@commands.has_guild_permissions(ban_members=True)
@commands.bot_has_guild_permissions(ban_members=True)
async def ban(
    ctx: commands.Context,
    member: discord.Member,
    *,
    reason: str | None = None,
) -> None:
    error = moderation_target_error(ctx, member)
    if error is not None:
        await send_moderation_error(ctx, error)
        return

    reason = reason.strip() if reason and reason.strip() else None
    if reason is not None and len(reason) > 400:
        await send_moderation_error(ctx, "The reason must be 400 characters or fewer.")
        return

    try:
        await member.ban(reason=reason)
    except discord.HTTPException as error:
        logger.warning(
            "Could not ban member %s in guild %s (HTTP %s).",
            member.id,
            member.guild.id,
            error.status,
        )
        await send_moderation_error(
            ctx,
            "Discord couldn't complete the ban. Check my permissions and try again.",
        )
        return

    await send_moderation_result(ctx, "Banned", member, reason)