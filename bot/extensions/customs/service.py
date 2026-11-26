import asyncio
from typing import Any

from bot.base.imports import commands, discord
from bot.extensions.customs import repository
from bot.extensions.customs.styles import supports_color_count

_guild_locks: dict[int, asyncio.Lock] = {}

RESET_PROFILE = {
    "nick": None,
    "avatar": None,
    "banner": None,
    "bio": None,
    "display_name_font_id": None,
    "display_name_effect_id": None,
    "display_name_colors": None,
}


class GuildNotWhitelisted(Exception):
    pass


class UnsupportedStyleCombination(Exception):
    pass


def discord_error_message(
    error: discord.HTTPException | discord.RateLimited,
) -> str:
    if isinstance(error, discord.RateLimited):
        return (
            "Discord rate-limited this request; retry in "
            f"{error.retry_after:.1f} seconds."
        )
    details = error.text or "Discord returned no additional details."
    if error.status == 403:
        return f"Discord denied the request or the feature is unavailable: {details}"
    if error.status == 429:
        return f"Discord rate-limited the request: {details}"
    return f"Discord rejected the request (HTTP {error.status}): {details}"


def _guild_lock(guild_id: int) -> asyncio.Lock:
    lock = _guild_locks.get(guild_id)
    if lock is None:
        lock = asyncio.Lock()
        _guild_locks[guild_id] = lock
    return lock


def _member_route(guild_id: int, user_id: int) -> discord.http.Route:
    return discord.http.Route(
        "GET",
        f"/guilds/{guild_id}/members/{user_id}",
    )


def _current_member_route(guild_id: int) -> discord.http.Route:
    return discord.http.Route(
        "PATCH",
        f"/guilds/{guild_id}/members/@me",
    )


def profile_snapshot(member: dict[str, Any]) -> dict[str, Any]:
    user = member.get("user")
    if not isinstance(user, dict):
        user = {}
    styles = member.get("display_name_styles")
    if not isinstance(styles, dict):
        styles = user.get("display_name_styles")
    if not isinstance(styles, dict):
        styles = {}

    return {
        "display_name": member.get("nick"),
        "avatar": member.get("avatar"),
        "banner": member.get("banner"),
        "bio": member.get("bio"),
        "display_name_font_id": member.get(
            "display_name_font_id",
            styles.get("font_id"),
        ),
        "display_name_effect_id": member.get(
            "display_name_effect_id",
            styles.get("effect_id"),
        ),
        "display_name_colors": member.get(
            "display_name_colors",
            styles.get("colors"),
        ),
    }


async def fetch_profile(
    bot: commands.Bot,
    guild_id: int,
) -> dict[str, Any]:
    if bot.user is None:
        raise RuntimeError("The bot user is unavailable before login.")
    member = await bot.http.request(_member_route(guild_id, bot.user.id))
    return profile_snapshot(member)


async def _apply_changes(
    bot: commands.Bot,
    guild_id: int,
    changes: dict[str, Any],
) -> dict[str, Any]:
    member = await bot.http.request(
        _current_member_route(guild_id),
        json=changes,
    )
    config = profile_snapshot(member)
    await repository.save_customizations(bot, guild_id, config)
    return config


async def apply_customization(
    bot: commands.Bot,
    guild_id: int,
    changes: dict[str, Any],
) -> dict[str, Any]:
    async with _guild_lock(guild_id):
        if not await repository.is_whitelisted(bot, guild_id):
            raise GuildNotWhitelisted
        return await _apply_changes(bot, guild_id, changes)


async def apply_display_name_colors(
    bot: commands.Bot,
    guild_id: int,
    colors: list[int],
) -> dict[str, Any]:
    async with _guild_lock(guild_id):
        if not await repository.is_whitelisted(bot, guild_id):
            raise GuildNotWhitelisted
        if bot.user is None:
            raise RuntimeError("The bot user is unavailable before login.")
        member = await bot.http.request(_member_route(guild_id, bot.user.id))
        current_profile = profile_snapshot(member)
        effect_id = current_profile["display_name_effect_id"]
        if not supports_color_count(effect_id, len(colors)):
            if len(colors) > 1:
                raise UnsupportedStyleCombination(
                    "Multiple colors require a supported gradient effect "
                    "(Gradient, Glow, Prism, or Gummy)."
                )
            raise UnsupportedStyleCombination(
                "The current effect is unknown or unsupported; select a "
                "verified effect or reset it before setting colors."
            )
        return await _apply_changes(
            bot,
            guild_id,
            {"display_name_colors": colors},
        )


async def whitelist_guild(
    bot: commands.Bot,
    guild_id: int,
) -> bool:
    async with _guild_lock(guild_id):
        if await repository.is_whitelisted(bot, guild_id):
            return False
        await repository.set_whitelisted(bot, guild_id, True)
        return True


async def reset_customizations(
    bot: commands.Bot,
    guild_id: int,
    *,
    revoke_access: bool = False,
) -> dict[str, Any]:
    async with _guild_lock(guild_id):
        if revoke_access:
            await repository.set_whitelisted(bot, guild_id, False)
        return await _apply_changes(bot, guild_id, RESET_PROFILE)
