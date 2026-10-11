import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg

from bot.base.imports import commands, discord, logger

MAX_TIMEOUT_SECONDS = 28 * 24 * 60 * 60
MAX_TIMEOUT_APPLY_SECONDS = MAX_TIMEOUT_SECONDS - 60
TIMEOUT_REFRESH_MARGIN_SECONDS = 24 * 60 * 60
TIMEOUT_RETRY_SECONDS = 5 * 60
TIMEOUT_POLL_SECONDS = 60


async def schedule_timeout_renewal(
    connection: asyncpg.Connection,
    guild_id: int,
    member_id: int,
    end_at: datetime,
    reason: str | None,
) -> None:
    now = datetime.now(UTC)
    next_refresh_at = min(
        end_at,
        now
        + timedelta(
            seconds=MAX_TIMEOUT_APPLY_SECONDS - TIMEOUT_REFRESH_MARGIN_SECONDS
        ),
    )
    await connection.execute(
        """
        INSERT INTO extended_timeouts (
            guild_id, member_id, end_at, next_refresh_at, reason
        )
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (guild_id, member_id)
        DO UPDATE SET
            end_at = EXCLUDED.end_at,
            next_refresh_at = EXCLUDED.next_refresh_at,
            reason = EXCLUDED.reason
        """,
        guild_id,
        member_id,
        end_at,
        next_refresh_at,
        reason,
    )


async def clear_scheduled_timeout(
    connection: asyncpg.Connection,
    guild_id: int,
    member_id: int,
) -> None:
    await connection.execute(
        """
        DELETE FROM extended_timeouts
        WHERE guild_id = $1 AND member_id = $2
        """,
        guild_id,
        member_id,
    )


async def timeout_renewal_loop(bot: commands.Bot) -> None:
    await bot.wait_until_ready()
    while not bot.is_closed():
        pool = getattr(bot, "database_pool", None)
        if pool is None:
            raise RuntimeError("Timeout renewals require the bot's database pool.")

        try:
            due_timeouts = await pool.fetch(
                """
                SELECT guild_id, member_id
                FROM extended_timeouts
                WHERE next_refresh_at <= NOW()
                ORDER BY next_refresh_at
                LIMIT 100
                """
            )
        except asyncpg.PostgresError:
            logger.exception("Could not load scheduled timeout renewals.")
            await asyncio.sleep(TIMEOUT_RETRY_SECONDS)
            continue

        for timeout_record in due_timeouts:
            try:
                await _renew_timeout(
                    bot,
                    pool,
                    timeout_record["guild_id"],
                    timeout_record["member_id"],
                )
            except asyncpg.PostgresError:
                logger.exception(
                    "Could not update scheduled timeout for member %s in guild %s.",
                    timeout_record["member_id"],
                    timeout_record["guild_id"],
                )
        await asyncio.sleep(TIMEOUT_POLL_SECONDS)


async def _renew_timeout(
    bot: commands.Bot,
    pool: asyncpg.Pool,
    guild_id: int,
    member_id: int,
) -> None:
    guild = bot.get_guild(guild_id)
    if guild is None:
        await clear_scheduled_timeout(pool, guild_id, member_id)
        return

    async with pool.acquire() as connection:
        async with connection.transaction():
            timeout_record = await connection.fetchrow(
                """
                SELECT end_at, reason
                FROM extended_timeouts
                WHERE guild_id = $1 AND member_id = $2
                  AND next_refresh_at <= NOW()
                FOR UPDATE
                """,
                guild_id,
                member_id,
            )
            if timeout_record is None:
                return

            try:
                member = guild.get_member(member_id)
                if member is None:
                    member = await guild.fetch_member(member_id)
            except discord.NotFound:
                await connection.execute(
                    """
                    DELETE FROM extended_timeouts
                    WHERE guild_id = $1 AND member_id = $2
                    """,
                    guild_id,
                    member_id,
                )
                return
            except discord.HTTPException as error:
                logger.warning(
                    "Could not fetch member %s for timeout renewal in guild %s "
                    "(HTTP %s).",
                    member_id,
                    guild_id,
                    error.status,
                )
                await _schedule_retry(connection, guild_id, member_id)
                return

            now = datetime.now(UTC)
            remaining_seconds = (timeout_record["end_at"] - now).total_seconds()
            if remaining_seconds <= 0:
                await connection.execute(
                    """
                    DELETE FROM extended_timeouts
                    WHERE guild_id = $1 AND member_id = $2
                    """,
                    guild_id,
                    member_id,
                )
                return

            timeout_seconds = min(
                MAX_TIMEOUT_APPLY_SECONDS,
                int(remaining_seconds),
            )
            try:
                await member.timeout(
                    timedelta(seconds=timeout_seconds),
                    reason=timeout_record["reason"],
                )
            except discord.NotFound:
                await connection.execute(
                    """
                    DELETE FROM extended_timeouts
                    WHERE guild_id = $1 AND member_id = $2
                    """,
                    guild_id,
                    member_id,
                )
                return
            except discord.HTTPException as error:
                logger.warning(
                    "Could not renew timeout for member %s in guild %s (HTTP %s).",
                    member_id,
                    guild_id,
                    error.status,
                )
                await _schedule_retry(connection, guild_id, member_id)
                return

            if remaining_seconds <= MAX_TIMEOUT_APPLY_SECONDS:
                await connection.execute(
                    """
                    DELETE FROM extended_timeouts
                    WHERE guild_id = $1 AND member_id = $2
                    """,
                    guild_id,
                    member_id,
                )
                return

            next_refresh_at = min(
                timeout_record["end_at"],
                now
                + timedelta(
                    seconds=(
                        MAX_TIMEOUT_APPLY_SECONDS
                        - TIMEOUT_REFRESH_MARGIN_SECONDS
                    )
                ),
            )
            await connection.execute(
                """
                UPDATE extended_timeouts
                SET next_refresh_at = $3
                WHERE guild_id = $1 AND member_id = $2
                """,
                guild_id,
                member_id,
                next_refresh_at,
            )


async def _schedule_retry(
    connection: asyncpg.Connection,
    guild_id: int,
    member_id: int,
) -> None:
    await connection.execute(
        """
        UPDATE extended_timeouts
        SET next_refresh_at = NOW() + ($3::BIGINT * INTERVAL '1 second')
        WHERE guild_id = $1 AND member_id = $2
        """,
        guild_id,
        member_id,
        TIMEOUT_RETRY_SECONDS,
    )
