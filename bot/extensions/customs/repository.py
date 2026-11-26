import json
from typing import Any

import asyncpg
from discord.ext import commands


def _pool(bot: commands.Bot) -> asyncpg.Pool:
    pool = getattr(bot, "database_pool", None)
    if pool is None:
        raise RuntimeError("The database pool is not initialized.")
    return pool


def _decode_customizations(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    return value if isinstance(value, dict) else {}


async def get_guild_record(
    bot: commands.Bot,
    guild_id: int,
) -> dict[str, Any] | None:
    row = await _pool(bot).fetchrow(
        """
        SELECT whitelisted, customizations
        FROM customs_guilds
        WHERE guild_id = $1
        """,
        guild_id,
    )
    if row is None:
        return None
    return {
        "whitelisted": row["whitelisted"],
        "customizations": _decode_customizations(row["customizations"]),
    }


async def is_whitelisted(bot: commands.Bot, guild_id: int) -> bool:
    value = await _pool(bot).fetchval(
        "SELECT whitelisted FROM customs_guilds WHERE guild_id = $1",
        guild_id,
    )
    return value is True


async def set_whitelisted(
    bot: commands.Bot,
    guild_id: int,
    whitelisted: bool,
) -> None:
    await _pool(bot).execute(
        """
        INSERT INTO customs_guilds (guild_id, whitelisted)
        VALUES ($1, $2)
        ON CONFLICT (guild_id) DO UPDATE
        SET whitelisted = EXCLUDED.whitelisted,
            updated_at = NOW()
        """,
        guild_id,
        whitelisted,
    )


async def save_customizations(
    bot: commands.Bot,
    guild_id: int,
    customizations: dict[str, Any],
) -> None:
    await _pool(bot).execute(
        """
        UPDATE customs_guilds
        SET customizations = $2::jsonb,
            updated_at = NOW()
        WHERE guild_id = $1
        """,
        guild_id,
        json.dumps(customizations),
    )
