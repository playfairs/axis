from __future__ import annotations

import asyncpg

from bot.base.imports import discord


async def count_message(
    message: discord.Message,
    *,
    database_pool: asyncpg.Pool | None,
) -> None:
    if (
        message.guild is None
        or message.author.bot
        or message.webhook_id is not None
    ):
        return
    if database_pool is None:
        raise RuntimeError("Message counting requires the bot's database pool.")

    await database_pool.execute(
        """
        INSERT INTO message_counts (guild_id, user_id, message_count)
        VALUES ($1, $2, 1)
        ON CONFLICT (guild_id, user_id)
        DO UPDATE SET message_count = message_counts.message_count + 1
        """,
        message.guild.id,
        message.author.id,
    )