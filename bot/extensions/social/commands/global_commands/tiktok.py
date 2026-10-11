import io
import os
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import aiohttp
import asyncpg
from discord import app_commands

from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord, logger

TIKTOK_URL_PATTERN = re.compile(
    r"https?://(?:(?:www|m|vm|vt)\.)?tiktok\.com/[^\s<>]+",
    re.IGNORECASE,
)
TIKWM_API_URL = "https://tikwm.com/api/"
TIKTOK_PROFILE_API_URL = os.getenv("TIKTOK_PROFILE_API_URL")
MAX_VIDEO_BYTES = 25 * 1024 * 1024
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class TikTokAPIError(Exception):
    pass


def _database_pool(bot: commands.Bot) -> asyncpg.Pool:
    pool = getattr(bot, "database_pool", None)
    if pool is None:
        raise RuntimeError("TikTok server settings require the bot's database pool.")
    return pool


def _format_number(value: object) -> str:
    if isinstance(value, bool):
        return "N/A"
    if isinstance(value, int):
        return f"{value:,}"
    if isinstance(value, str):
        try:
            return f"{int(value):,}"
        except ValueError:
            return value
    return "N/A"


async def _request_json(
    session: aiohttp.ClientSession,
    url: str,
    *,
    params: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    try:
        async with session.get(url, params=params) as response:
            if response.status != 200:
                raise TikTokAPIError(f"The service returned HTTP {response.status}.")
            payload = await response.json()
    except (aiohttp.ClientError, TimeoutError, ValueError) as error:
        raise TikTokAPIError("The TikTok service could not be reached.") from error

    if not isinstance(payload, dict):
        raise TikTokAPIError("The TikTok service returned an invalid response.")
    return payload


async def _download_video(
    session: aiohttp.ClientSession,
    url: str,
) -> bytes:
    try:
        async with session.get(url) as response:
            if response.status != 200:
                raise TikTokAPIError(
                    f"The video service returned HTTP {response.status}."
                )
            content_length = response.content_length
            if content_length is not None and content_length > MAX_VIDEO_BYTES:
                raise TikTokAPIError("The video is too large to upload.")

            video = bytearray()
            async for chunk in response.content.iter_chunked(64 * 1024):
                video.extend(chunk)
                if len(video) > MAX_VIDEO_BYTES:
                    raise TikTokAPIError("The video is too large to upload.")
    except (aiohttp.ClientError, TimeoutError) as error:
        raise TikTokAPIError("The TikTok video could not be downloaded.") from error
    return bytes(video)


async def _fetch_video(
    session: aiohttp.ClientSession,
    url: str,
) -> tuple[dict[str, Any], bytes]:
    payload = await _request_json(
        session,
        TIKWM_API_URL,
        params={"url": url},
    )
    data = payload.get("data")
    if payload.get("code") not in (None, 0) or not isinstance(data, dict):
        raise TikTokAPIError("TikTok could not provide that video.")

    video_url = data.get("play")
    author = data.get("author")
    if not isinstance(video_url, str) or not video_url:
        raise TikTokAPIError("The TikTok response did not include a video.")
    if not isinstance(author, dict):
        author = {}
    video = await _download_video(session, video_url)
    return {
        "video": video,
        "title": data.get("title"),
        "likes": data.get("digg_count"),
        "comments": data.get("comment_count"),
        "shares": data.get("share_count"),
        "username": author.get("unique_id"),
        "avatar": author.get("avatar"),
    }, video


def _video_view(
    data: Mapping[str, Any],
    video_url: str,
    filename: str,
) -> discord.ui.LayoutView:
    title = data.get("title")
    description = (
        title[:3500]
        if isinstance(title, str) and title
        else "No description provided."
    )
    username = data.get("username")
    creator_link = (
        f"**[@{username} on TikTok](https://www.tiktok.com/@{quote(username, safe='')})**"
        if isinstance(username, str) and username
        else f"**[TikTok video]({video_url})**"
    )
    stats = (
        f"❤️ **Likes:** {_format_number(data.get('likes'))}  ·  "
        f"💬 **Comments:** {_format_number(data.get('comments'))}  ·  "
        f"🔗 **Shares:** {_format_number(data.get('shares'))}"
    )

    view = discord.ui.LayoutView()
    view.add_item(
        discord.ui.Container(
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    f"attachment://{filename}",
                    description="TikTok video",
                )
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"{creator_link}\n{description}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(stats),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"[Watch on TikTok]({video_url})"),
            accent_color=DEFAULT_CONTAINER_COLOR,
        )
    )
    return view


@commands.hybrid_group(
    name="tiktok",
    aliases=("tt",),
    invoke_without_command=True,
    description="Look up TikTok users and repost TikTok videos.",
)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def tiktok(ctx: commands.Context) -> None:
    await ctx.send_help(ctx.command)


@tiktok.command(name="user", description="Get TikTok user information.")
@app_commands.describe(username="The TikTok username.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def tiktok_user(
    ctx: commands.Context,
    username: str | None = None,
) -> None:
    if username is None:
        await ctx.send(
            "Please provide a TikTok username.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    if not TIKTOK_PROFILE_API_URL:
        logger.error("TIKTOK_PROFILE_API_URL is not configured.")
        await ctx.send(
            "TikTok profile lookup is not configured.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    username = username.strip().removeprefix("@")
    if not username:
        await ctx.send(
            "Please provide a TikTok username.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        try:
            data = await _request_json(
                session,
                TIKTOK_PROFILE_API_URL.format(username=quote(username, safe="")),
            )
        except TikTokAPIError as error:
            logger.warning("TikTok profile lookup failed for %s: %s", username, error)
            await ctx.send(
                f"Couldn't retrieve that TikTok profile: {error}",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

    unique_id = data.get("unique_id")
    nickname = data.get("nickname")
    if not isinstance(unique_id, str) or not unique_id:
        await ctx.send(
            "TikTok didn't return a valid profile for that username.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    signature = data.get("signature")
    description = None
    if isinstance(signature, str) and signature:
        description = "\n".join(
            f"-# {line}" for line in signature.splitlines() if line
        )[:250]

    embed = discord.Embed(
        title=f"{unique_id} ({nickname})" if nickname else unique_id,
        url=f"https://www.tiktok.com/@{quote(unique_id, safe='')}",
        description=description,
    )
    avatar_url = data.get("avatar_larger")
    if isinstance(avatar_url, str) and avatar_url:
        embed.set_thumbnail(url=avatar_url)
    embed.set_footer(text="tiktok.com")
    for label, key in (
        ("Followers", "followers"),
        ("Following", "following"),
        ("Likes", "likes"),
    ):
        embed.add_field(name=label, value=f"`{_format_number(data.get(key))}`")
    await ctx.send(
        embed=embed,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@tiktok.command(name="repost", description="Repost a TikTok video.")
@app_commands.describe(url="The link to the TikTok video.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def tiktok_repost(
    ctx: commands.Context,
    url: str | None = None,
) -> None:
    if url is None:
        await ctx.send(
            "Please provide a link to a TikTok video.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    url = url.strip()
    if TIKTOK_URL_PATTERN.fullmatch(url) is None:
        await ctx.send(
            "Please provide a valid TikTok video link.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        try:
            data, video = await _fetch_video(session, url)
        except TikTokAPIError as error:
            logger.warning("TikTok video repost failed: %s", error)
            await ctx.send(
                f"Couldn't repost that TikTok video: {error}",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

    filename = "tiktok.mp4"
    await ctx.send(
        view=_video_view(data, url, filename),
        file=discord.File(io.BytesIO(video), filename=filename),
        allowed_mentions=discord.AllowedMentions.none(),
    )
    if ctx.interaction is None:
        try:
            await ctx.message.delete()
        except discord.Forbidden:
            logger.info("Could not delete TikTok repost command message.")
        except discord.HTTPException as error:
            logger.warning(
                "Could not delete TikTok repost command message (HTTP %s).",
                error.status,
            )


@tiktok.command(name="enable", description="Enable automatic TikTok reposts here.")
@app_commands.allowed_contexts(guilds=True, dms=False, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def tiktok_enable(ctx: commands.Context) -> None:
    if ctx.guild is None:
        await ctx.send(
            "This setting can only be changed in a server.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    await _database_pool(ctx.bot).execute(
        """
        INSERT INTO tiktok_reposter (guild_id, enabled)
        VALUES ($1, TRUE)
        ON CONFLICT (guild_id) DO UPDATE SET enabled = TRUE
        """,
        ctx.guild.id,
    )
    await ctx.send(
        "Automatic TikTok reposts are enabled in this server.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@tiktok.command(name="disable", description="Disable automatic TikTok reposts here.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def tiktok_disable(ctx: commands.Context) -> None:
    if ctx.guild is None:
        await ctx.send(
            "This setting can only be changed in a server.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    await _database_pool(ctx.bot).execute(
        """
        INSERT INTO tiktok_reposter (guild_id, enabled)
        VALUES ($1, FALSE)
        ON CONFLICT (guild_id) DO UPDATE SET enabled = FALSE
        """,
        ctx.guild.id,
    )
    await ctx.send(
        "Automatic TikTok reposts are disabled in this server.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def on_message(bot: commands.Bot, message: discord.Message) -> None:
    if (
        message.author.bot
        or message.guild is None
        or message.type is not discord.MessageType.default
    ):
        return

    match = TIKTOK_URL_PATTERN.search(message.content)
    if match is None:
        return

    context = await bot.get_context(message)
    context.view.skip_ws()
    if (
        context.command is tiktok
        and context.view.get_word().casefold() == "repost"
    ):
        return

    pool = _database_pool(bot)
    try:
        setting = await pool.fetchrow(
            "SELECT enabled FROM tiktok_reposter WHERE guild_id = $1",
            message.guild.id,
        )
    except asyncpg.PostgresError:
        logger.exception(
            "Could not read TikTok repost settings for guild %s.",
            message.guild.id,
        )
        return
    if setting is None or not setting["enabled"]:
        return

    async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
        try:
            data, video = await _fetch_video(session, match.group())
        except TikTokAPIError as error:
            logger.warning(
                "Automatic TikTok repost failed in guild %s: %s",
                message.guild.id,
                error,
            )
            await message.channel.send(
                f"Couldn't repost that TikTok video: {error}",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

    filename = "tiktok.mp4"
    await message.channel.send(
        view=_video_view(data, match.group(), filename),
        file=discord.File(io.BytesIO(video), filename=filename),
        allowed_mentions=discord.AllowedMentions.none(),
    )
    try:
        await message.delete()
    except discord.Forbidden:
        logger.info(
            "Could not delete TikTok link message %s in guild %s.",
            message.id,
            message.guild.id,
        )
    except discord.HTTPException as error:
        logger.warning(
            "Could not delete TikTok link message %s in guild %s (HTTP %s).",
            message.id,
            message.guild.id,
            error.status,
        )


listeners = {"on_message": on_message}
