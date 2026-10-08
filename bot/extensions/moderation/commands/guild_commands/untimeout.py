from bot.base.imports import commands, discord, logger
from bot.extensions.moderation._checks import (
    moderation_target_error,
    send_moderation_error,
    send_moderation_result,
)


@commands.command(
    name="untimeout",
    aliases=["unto", "uto", "rto", "removetimeout"],
    description="Remove a member's timeout in this server.",
)
@commands.guild_only()
@commands.has_guild_permissions(moderate_members=True)
@commands.bot_has_guild_permissions(moderate_members=True)
async def untimeout(
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
        await member.timeout(None, reason=reason)
    except discord.HTTPException as error:
        logger.warning(
            "Could not remove timeout from member %s in guild %s (HTTP %s).",
            member.id,
            member.guild.id,
            error.status,
        )
        await send_moderation_error(
            ctx,
            "Discord couldn't remove the timeout. Check my permissions and try again.",
        )
        return

    await send_moderation_result(ctx, "Removed timeout from", member, reason)
