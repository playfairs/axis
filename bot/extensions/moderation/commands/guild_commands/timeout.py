import re
from datetime import UTC, datetime, timedelta

from bot.base.imports import commands, discord, logger
from bot.extensions.moderation.timeouts import (
    MAX_TIMEOUT_APPLY_SECONDS,
    clear_scheduled_timeout,
    schedule_timeout_renewal,
)
from bot.extensions.moderation._checks import (
    moderation_target_error,
    send_moderation_error,
    send_moderation_result,
)

DURATION_TOKEN = re.compile(
    r"(\d+)(years?|yrs?|y|weeks?|w|days?|d|hours?|h|minutes?|mins?|m|seconds?|secs?|s)",
    re.IGNORECASE,
)
DURATION_SEQUENCE = re.compile(
    r"(?P<duration>(?:\d+\s*(?:years?|yrs?|y|weeks?|w|days?|d|hours?|h|minutes?|mins?|m|seconds?|secs?|s)\s*)+)"
    r"(?:\s+(?P<reason>.*))?",
    re.IGNORECASE,
)
DURATION_UNITS = {
    "y": 365 * 24 * 60 * 60,
    "yr": 365 * 24 * 60 * 60,
    "yrs": 365 * 24 * 60 * 60,
    "year": 365 * 24 * 60 * 60,
    "years": 365 * 24 * 60 * 60,
    "w": 7 * 24 * 60 * 60,
    "week": 7 * 24 * 60 * 60,
    "weeks": 7 * 24 * 60 * 60,
    "d": 24 * 60 * 60,
    "day": 24 * 60 * 60,
    "days": 24 * 60 * 60,
    "h": 60 * 60,
    "hour": 60 * 60,
    "hours": 60 * 60,
    "m": 60,
    "min": 60,
    "mins": 60,
    "minute": 60,
    "minutes": 60,
    "s": 1,
    "sec": 1,
    "secs": 1,
    "second": 1,
    "seconds": 1,
}
MAX_SCHEDULABLE_TIMEOUT_SECONDS = 250_000_000_000


def _parse_duration(value: str) -> timedelta:
    compact = "".join(value.split())
    if not compact:
        raise ValueError("Enter a timeout duration.")

    seconds = 0
    position = 0
    for match in DURATION_TOKEN.finditer(compact):
        if match.start() != position:
            raise ValueError("Use a duration such as `30m`, `1h30m`, or `1 day`.")
        try:
            amount = int(match.group(1))
        except ValueError as error:
            raise ValueError("That timeout duration is too large.") from error
        seconds += amount * DURATION_UNITS[match.group(2).casefold()]
        if seconds > MAX_SCHEDULABLE_TIMEOUT_SECONDS:
            raise ValueError("That timeout duration is too large to schedule.")
        position = match.end()

    if position != len(compact):
        raise ValueError("Use a duration such as `30m`, `1h30m`, or `1 day`.")
    if seconds == 0:
        raise ValueError("Timeout duration must be greater than zero.")
    return timedelta(seconds=seconds)


def _format_duration(duration: timedelta) -> str:
    seconds = int(duration.total_seconds())
    parts: list[str] = []
    for unit_seconds, unit_name in (
        (365 * 24 * 60 * 60, "y"),
        (7 * 24 * 60 * 60, "w"),
        (24 * 60 * 60, "d"),
        (60 * 60, "h"),
        (60, "m"),
        (1, "s"),
    ):
        amount, seconds = divmod(seconds, unit_seconds)
        if amount:
            parts.append(f"{amount}{unit_name}")
    return " ".join(parts)


def _parse_duration_and_reason(
    value: str | None,
) -> tuple[timedelta, str | None]:
    if value is None or not value.strip():
        return timedelta(minutes=5), None

    value = value.strip()
    match = DURATION_SEQUENCE.fullmatch(value)
    if match is None:
        if value[0].isdigit():
            raise ValueError(
                "Use a duration such as `10m`, `1h30m`, `1y`, or "
                "`1 hour 30 minutes`."
            )
        return timedelta(minutes=5), value

    duration = _parse_duration(match.group("duration"))
    reason = (match.group("reason") or "").strip() or None
    return duration, reason


@commands.command(
    name="timeout",
    aliases=["to"],
    description="Temporarily prevent a member from interacting in this server.",
)
@commands.guild_only()
@commands.has_guild_permissions(moderate_members=True)
@commands.bot_has_guild_permissions(moderate_members=True)
async def timeout(
    ctx: commands.Context,
    member: discord.Member,
    *,
    duration_and_reason: str | None = None,
) -> None:
    error = moderation_target_error(ctx, member)
    if error is not None:
        await send_moderation_error(ctx, error)
        return

    try:
        timeout_duration, reason = _parse_duration_and_reason(duration_and_reason)
    except ValueError as error:
        await send_moderation_error(ctx, str(error))
        return

    if reason is not None and len(reason) > 400:
        await send_moderation_error(ctx, "The reason must be 400 characters or fewer.")
        return

    end_at = datetime.now(UTC) + timeout_duration
    pool = getattr(ctx.bot, "database_pool", None)
    if pool is None:
        raise RuntimeError("The timeout command requires the bot's database pool.")

    try:
        async with pool.acquire() as connection:
            async with connection.transaction():
                if timeout_duration.total_seconds() > MAX_TIMEOUT_APPLY_SECONDS:
                    await schedule_timeout_renewal(
                        connection,
                        member.guild.id,
                        member.id,
                        end_at,
                        reason,
                    )
                    await member.timeout(
                        timedelta(seconds=MAX_TIMEOUT_APPLY_SECONDS),
                        reason=reason,
                    )
                else:
                    await clear_scheduled_timeout(
                        connection,
                        member.guild.id,
                        member.id,
                    )
                    await member.timeout(timeout_duration, reason=reason)
    except discord.HTTPException as error:
        logger.warning(
            "Could not timeout member %s in guild %s (HTTP %s).",
            member.id,
            member.guild.id,
            error.status,
        )
        await send_moderation_error(
            ctx,
            "Discord couldn't complete the timeout. Check my permissions and try again.",
        )
        return

    await send_moderation_result(
        ctx,
        "Timed out",
        member,
        reason,
        duration=_format_duration(timeout_duration),
    )
