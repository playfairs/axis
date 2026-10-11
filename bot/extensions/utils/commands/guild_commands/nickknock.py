import re

import asyncpg
from discord import app_commands

from bot.base.imports import commands
from bot.events.listeners.nickknock import reset_guild_cooldown

MAX_INTERVAL_SECONDS = 2**63 - 1
MAX_SLASH_VALUE = 2**53 - 1
PREFIX_INTERVAL_PATTERN = re.compile(
    r"^\s*(\d+)\s*(seconds?|minutes?|hours?|s|m|h)\s*$",
    re.IGNORECASE,
)
UNIT_SECONDS = {
    "s": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "minute": 60,
    "minutes": 60,
    "h": 60 * 60,
    "hour": 60 * 60,
    "hours": 60 * 60,
}


def _database_pool(bot: object) -> asyncpg.Pool:
    pool = getattr(bot, "database_pool", None)
    if pool is None:
        raise RuntimeError("The nickknock command requires the bot's database pool.")
    return pool


async def _set_enabled(
    pool: asyncpg.Pool,
    guild_id: int,
    enabled: bool,
) -> None:
    await pool.execute(
        """
        INSERT INTO nickknock_settings (guild_id, enabled)
        VALUES ($1, $2)
        ON CONFLICT (guild_id)
        DO UPDATE SET enabled = EXCLUDED.enabled
        """,
        guild_id,
        enabled,
    )
    reset_guild_cooldown(guild_id)


async def _set_interval(
    pool: asyncpg.Pool,
    guild_id: int,
    interval_seconds: int,
) -> None:
    await pool.execute(
        """
        INSERT INTO nickknock_settings (guild_id, interval_seconds)
        VALUES ($1, $2)
        ON CONFLICT (guild_id)
        DO UPDATE SET interval_seconds = EXCLUDED.interval_seconds
        """,
        guild_id,
        interval_seconds,
    )
    reset_guild_cooldown(guild_id)


def _parse_prefix_interval(value: str) -> int | None:
    match = PREFIX_INTERVAL_PATTERN.fullmatch(value)
    if match is None or len(match.group(1)) > 19:
        return None

    amount = int(match.group(1))
    interval_seconds = amount * UNIT_SECONDS[match.group(2).lower()]
    if amount <= 0 or interval_seconds > MAX_INTERVAL_SECONDS:
        return None
    return interval_seconds


def _interval_response(interval_seconds: int) -> str:
    return f"Nickknock interval set to {interval_seconds} seconds."


@commands.hybrid_group(
    name="nickknock",
    aliases=["nk", "iam"],
    invoke_without_command=True,
    description="Enable, disable, or configure nickname knocking.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def nickknock(ctx: commands.Context) -> None:
    await ctx.send(
        "Use `nickknock enable`, `nickknock disable`, or "
        "`nickknock interval <number><unit>`."
    )


@nickknock.command(name="enable", description="Enable nickname knocking.")
async def nickknock_enable(ctx: commands.Context) -> None:
    if ctx.guild is None:
        raise RuntimeError("The nickknock command must be used in a server.")
    await _set_enabled(_database_pool(ctx.bot), ctx.guild.id, True)
    await ctx.send("Nickknock is enabled in this server.")


@nickknock.command(name="disable", description="Disable nickname knocking.")
async def nickknock_disable(ctx: commands.Context) -> None:
    if ctx.guild is None:
        raise RuntimeError("The nickknock command must be used in a server.")
    await _set_enabled(_database_pool(ctx.bot), ctx.guild.id, False)
    await ctx.send("Nickknock is disabled in this server.")


@nickknock.command(
    name="interval",
    aliases=["int", "duration", "cooldown"],
    description="Set the nickname knocking cooldown.",
)
@app_commands.describe(
    value="A duration such as 30s, 5minutes, or 2h; unit can also be selected.",
    unit="The time unit.",
)
@app_commands.choices(
    unit=[
        app_commands.Choice(name="Seconds", value="seconds"),
        app_commands.Choice(name="Minutes", value="minutes"),
        app_commands.Choice(name="Hours", value="hours"),
    ]
)
async def nickknock_interval(
    ctx: commands.Context,
    value: str,
    unit: str | None = None,
) -> None:
    if ctx.guild is None:
        raise RuntimeError("The nickknock command must be used in a server.")

    if unit is not None:
        if unit not in UNIT_SECONDS:
            await ctx.send("Choose Seconds, Minutes, or Hours.")
            return
        try:
            amount = int(value)
        except ValueError:
            amount = 0
        interval_seconds = amount * UNIT_SECONDS[unit]
        if (
            amount <= 0
            or amount > MAX_INTERVAL_SECONDS
            or interval_seconds > MAX_INTERVAL_SECONDS
        ):
            interval_seconds = None
    else:
        interval_seconds = _parse_prefix_interval(value)

    if interval_seconds is None:
        await ctx.send(
            "Use a positive interval such as `30s`, `5minutes`, or `2h`."
        )
        return
    await _set_interval(_database_pool(ctx.bot), ctx.guild.id, interval_seconds)
    await ctx.send(_interval_response(interval_seconds))