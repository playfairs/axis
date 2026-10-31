import asyncio

import asyncpg

from bot.base.imports import commands, discord, logger

WATER_POLL_SECONDS = 30
WATER_RETRY_SECONDS = 60
WATER_MESSAGE = "💧 **It's time to drink water!**"


async def water_reminder_loop(bot: commands.Bot) -> None:
    await bot.wait_until_ready()
    while not bot.is_closed():
        pool = getattr(bot, "database_pool", None)
        if pool is None:
            raise RuntimeError("Water reminders require the bot's database pool.")

        try:
            reminders = await pool.fetch(
                """
                SELECT guild_id, channel_id, interval_seconds, ping_member_ids
                FROM water_settings
                WHERE enabled
                  AND channel_id IS NOT NULL
                  AND next_reminder_at <= NOW()
                ORDER BY next_reminder_at
                LIMIT 100
                """
            )
        except asyncpg.PostgresError:
            logger.exception("Could not load scheduled water reminders.")
            await asyncio.sleep(WATER_RETRY_SECONDS)
            continue

        for reminder in reminders:
            try:
                await send_water_reminder(
                    bot,
                    pool,
                    guild_id=reminder["guild_id"],
                    channel_id=reminder["channel_id"],
                    interval_seconds=reminder["interval_seconds"],
                    ping_member_ids=reminder["ping_member_ids"],
                )
            except asyncpg.PostgresError:
                logger.exception(
                    "Could not update water reminder for guild %s.",
                    reminder["guild_id"],
                )
        await asyncio.sleep(WATER_POLL_SECONDS)


async def send_water_reminder(
    bot: commands.Bot,
    pool: asyncpg.Pool,
    *,
    guild_id: int,
    channel_id: int,
    interval_seconds: int,
    ping_member_ids: list[int],
) -> bool:
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.NotFound:
            logger.warning(
                "Water reminder channel %s in guild %s no longer exists.",
                channel_id,
                guild_id,
            )
            await _schedule_retry(pool, guild_id)
            return False
        except discord.HTTPException as error:
            logger.warning(
                "Could not fetch water reminder channel %s in guild %s "
                "(HTTP %s).",
                channel_id,
                guild_id,
                error.status,
            )
            await _schedule_retry(pool, guild_id)
            return False

    if not isinstance(channel, discord.TextChannel) or channel.guild.id != guild_id:
        logger.warning(
            "Water reminder channel %s is not a text channel in guild %s.",
            channel_id,
            guild_id,
        )
        await _schedule_retry(pool, guild_id)
        return False

    guild = channel.guild
    members = [
        member
        for member_id in ping_member_ids
        if (member := guild.get_member(member_id)) is not None
    ]
    mentions = ", ".join(member.mention for member in members)
    content = f"{mentions}, {WATER_MESSAGE}" if mentions else WATER_MESSAGE
    try:
        await channel.send(
            content,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=members,
                roles=False,
                replied_user=False,
            ),
        )
    except discord.HTTPException as error:
        logger.warning(
            "Could not send water reminder in channel %s in guild %s "
            "(HTTP %s).",
            channel_id,
            guild_id,
            error.status,
        )
        await _schedule_retry(pool, guild_id)
        return False

    await pool.execute(
        """
        UPDATE water_settings
        SET next_reminder_at = NOW() + ($2::BIGINT * INTERVAL '1 second')
        WHERE guild_id = $1 AND enabled
        """,
        guild_id,
        interval_seconds,
    )
    return True


async def _schedule_retry(pool: asyncpg.Pool, guild_id: int) -> None:
    await pool.execute(
        """
        UPDATE water_settings
        SET next_reminder_at = NOW() + ($2::BIGINT * INTERVAL '1 second')
        WHERE guild_id = $1 AND enabled
        """,
        guild_id,
        WATER_RETRY_SECONDS,
    )
