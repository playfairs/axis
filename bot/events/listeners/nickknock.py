import re
import time

import asyncpg

from bot.base.imports import discord, logger

AM_I_NICKNAME_PATTERN = re.compile(
    r"\bam\s+i\b\s+(.+?)\s*[.!?]*\s*$",
    re.IGNORECASE,
)
NICKNAME_PATTERN = re.compile(
    r"^\s*i\s*(?:['’‘`´]\s*m|m|am)\s+(.+?)\s*$",
    re.IGNORECASE,
)
NICKKNOCK_BOT_ID = 974297735559806986
_guild_cooldowns: dict[int, float] = {}


def reset_guild_cooldown(guild_id: int) -> None:
    _guild_cooldowns.pop(guild_id, None)


async def on_message(
    message: discord.Message,
    *,
    database_pool: asyncpg.Pool | None,
) -> None:
    if (
        message.guild is None
        or (message.author.bot and message.author.id != NICKKNOCK_BOT_ID)
        or not isinstance(message.author, discord.Member)
    ):
        return

    if database_pool is None:
        raise RuntimeError("The nickknock listener requires the bot's database pool.")

    match = AM_I_NICKNAME_PATTERN.search(message.content)
    is_am_i = match is not None
    if match is None:
        match = NICKNAME_PATTERN.fullmatch(message.content)
    if match is None:
        return

    nickname = match.group(1).strip()
    if is_am_i:
        nickname = nickname.rstrip(".!?").rstrip()
    if not nickname or len(nickname) > 32:
        return

    settings = await database_pool.fetchrow(
        """
        SELECT enabled, interval_seconds
        FROM nickknock_settings
        WHERE guild_id = $1
        """,
        message.guild.id,
    )
    if settings is None or not settings["enabled"]:
        return

    now = time.monotonic()
    cooldown_expires = _guild_cooldowns.get(message.guild.id, 0.0)
    if now < cooldown_expires:
        return

    cooldown_expires = now + settings["interval_seconds"]
    _guild_cooldowns[message.guild.id] = cooldown_expires
    try:
        await message.reply(
            f"Yes, you're {nickname}" if is_am_i else f"Hi {nickname}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException as error:
        if _guild_cooldowns.get(message.guild.id) == cooldown_expires:
            del _guild_cooldowns[message.guild.id]
        logger.warning(
            "Could not send nickname greeting for member %s in guild %s (HTTP %s).",
            message.author.id,
            message.guild.id,
            error.status,
        )
        return

    try:
        await message.author.edit(nick=nickname)
    except discord.HTTPException as error:
        if _guild_cooldowns.get(message.guild.id) == cooldown_expires:
            del _guild_cooldowns[message.guild.id]
        logger.warning(
            "Could not set nickname for member %s in guild %s (HTTP %s).",
            message.author.id,
            message.guild.id,
            error.status,
        )