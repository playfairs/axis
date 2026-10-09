from bot.base.imports import commands, discord, logger
from bot.extensions.moderation._checks import (
    moderation_target_error,
    send_moderation_error,
    send_moderation_result,
)


@commands.command(
    name="nick",
    description="Change or reset a member's nickname in this server.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_nicknames=True)
@commands.bot_has_guild_permissions(manage_nicknames=True)
async def nick(
    ctx: commands.Context,
    member: discord.Member,
    *,
    nickname: str | None = None,
) -> None:
    error = moderation_target_error(ctx, member)
    if error is not None:
        await send_moderation_error(ctx, error)
        return

    nickname = nickname.strip() if nickname and nickname.strip() else None
    if nickname is not None and len(nickname) > 32:
        await send_moderation_error(ctx, "Nicknames must be 32 characters or fewer.")
        return

    try:
        await member.edit(nick=nickname)
    except discord.HTTPException as error:
        logger.warning(
            "Could not change nickname for member %s in guild %s (HTTP %s).",
            member.id,
            member.guild.id,
            error.status,
        )
        await send_moderation_error(
            ctx,
            "Discord couldn't change that nickname. Check my permissions and try again.",
        )
        return

    action = "Reset nickname for" if nickname is None else "Changed nickname for"
    await send_moderation_result(ctx, action, member, None)
