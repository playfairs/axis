from bot.base.imports import commands, discord, logger
from bot.extensions.moderation._checks import (
    moderation_target_error,
    send_moderation_error,
    send_moderation_result,
)


@commands.command(
    name="ban",
    description="Ban a user from this server by member or user ID.",
)
@commands.guild_only()
@commands.has_guild_permissions(ban_members=True)
@commands.bot_has_guild_permissions(ban_members=True)
async def ban(
    ctx: commands.Context,
    target: discord.Member | discord.User,
    *,
    reason: str | None = None,
) -> None:
    guild = ctx.guild
    if guild is None:
        await send_moderation_error(ctx, "This command can only be used in a server.")
        return

    member = (
        target
        if isinstance(target, discord.Member)
        else guild.get_member(target.id)
    )
    if member is None:
        try:
            member = await guild.fetch_member(target.id)
        except discord.NotFound:
            pass
        except discord.HTTPException as error:
            logger.warning(
                "Could not check whether user %s is a member of guild %s (HTTP %s).",
                target.id,
                guild.id,
                error.status,
            )
            await send_moderation_error(
                ctx,
                "I couldn't check whether that user is in this server. Please try "
                "again.",
            )
            return

    if member is not None:
        error = moderation_target_error(ctx, member)
        if error is not None:
            await send_moderation_error(ctx, error)
            return
    else:
        if not isinstance(ctx.author, discord.Member):
            await send_moderation_error(ctx, "Your server role couldn't be verified.")
            return
        if target.id == ctx.author.id:
            await send_moderation_error(ctx, "You can't take action on yourself.")
            return
        if target.id == guild.owner_id:
            await send_moderation_error(
                ctx,
                "You can't take action on the server owner.",
            )
            return
        bot_member = guild.me
        if bot_member is None:
            await send_moderation_error(
                ctx,
                "I couldn't verify my role in this server.",
            )
            return
        if target.id == bot_member.id:
            await send_moderation_error(ctx, "I can't take action on myself.")
            return

    reason = reason.strip() if reason and reason.strip() else None
    if reason is not None and len(reason) > 400:
        await send_moderation_error(ctx, "The reason must be 400 characters or fewer.")
        return

    try:
        await guild.ban(target, reason=reason)
    except discord.HTTPException as error:
        logger.warning(
            "Could not ban user %s in guild %s (HTTP %s).",
            target.id,
            guild.id,
            error.status,
        )
        await send_moderation_error(
            ctx,
            "Discord couldn't complete the ban. Check my permissions and try again.",
        )
        return

    await send_moderation_result(ctx, "Banned", target, reason)