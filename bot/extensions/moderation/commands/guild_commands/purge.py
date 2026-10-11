import re
from collections.abc import Callable
from urllib.parse import urlsplit

from discord import app_commands

from bot.base.imports import commands, discord, logger

DEFAULT_PURGE_LIMIT = 100
MAX_PURGE_LIMIT = 1000
URL_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
INVITE_PATTERN = re.compile(
    r"(?:discord(?:app)?\.com/invite|discord\.gg)/[A-Za-z0-9-]+",
    re.IGNORECASE,
)

async def _defer(ctx: commands.Context) -> None:
    if ctx.interaction is not None and not ctx.interaction.response.is_done():
        await ctx.defer(ephemeral=True)


async def _send_result(ctx: commands.Context, content: str) -> None:
    await ctx.send(
        content,
        ephemeral=ctx.interaction is not None,
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def _valid_count(ctx: commands.Context, count: int) -> bool:
    if 1 <= count <= MAX_PURGE_LIMIT:
        return True
    await _send_result(ctx, f"Choose a count between 1 and {MAX_PURGE_LIMIT}.")
    return False


def _message_link(message: discord.Message) -> str:
    return (
        f"https://discord.com/channels/"
        f"{message.guild.id if message.guild else '@me'}/"
        f"{message.channel.id}/{message.id}"
    )


async def _purge_messages(
    ctx: commands.Context,
    check: Callable[[discord.Message], bool],
    *,
    limit: int = DEFAULT_PURGE_LIMIT,
    before: discord.Message | None = None,
    after: discord.Message | None = None,
    result: Callable[[int], str] | None = None,
) -> None:
    if not await _valid_count(ctx, limit):
        return

    channel = ctx.channel
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        await _send_result(ctx, "Messages can't be purged from this channel.")
        return

    await _defer(ctx)
    try:
        deleted = await channel.purge(
            limit=limit,
            check=check,
            before=before,
            after=after,
            reason=f"Purged by {ctx.author} ({ctx.author.id})",
        )
    except discord.HTTPException as error:
        logger.warning(
            "Could not purge messages in channel %s (HTTP %s).",
            channel.id,
            error.status,
        )
        await _send_result(
            ctx,
            "Discord couldn't delete those messages. Check my permissions and try again.",
        )
        return

    result_message = result or (lambda count: f"Purged **{count}** messages.")
    await _send_result(ctx, result_message(len(deleted)))


def _is_gif_url(url: str) -> bool:
    cleaned_url = url.rstrip(".,!?;:)]}")
    host = urlsplit(cleaned_url).hostname
    return (
        cleaned_url.casefold().split("?", 1)[0].endswith((".gif", ".gifv"))
        or (
            host is not None
            and any(
                host.casefold() == domain or host.casefold().endswith(f".{domain}")
                for domain in ("giphy.com", "tenor.com")
            )
        )
    )


def _message_urls(message: discord.Message) -> list[str]:
    urls = URL_PATTERN.findall(message.content)
    for embed in message.embeds:
        urls.extend(
            url
            for url in (
                embed.url,
                embed.image.url if embed.image else None,
                embed.thumbnail.url if embed.thumbnail else None,
                embed.video.url if embed.video else None,
            )
            if url is not None
        )
    return urls


def _message_has_gif(message: discord.Message) -> bool:
    for attachment in message.attachments:
        if (
            attachment.content_type == "image/gif"
            or attachment.filename.casefold().endswith((".gif", ".gifv"))
        ):
            return True

    if any(_is_gif_url(url) for url in _message_urls(message)):
        return True
    return any(embed.type == "gifv" for embed in message.embeds)


@commands.hybrid_group(
    name="purge",
    aliases=("c", "clear"),
    description="Delete messages from this server.",
    invoke_without_command=True,
)
@commands.guild_only()
@commands.has_guild_permissions(manage_messages=True)
@commands.bot_has_guild_permissions(manage_messages=True)
@app_commands.guild_only()
@app_commands.default_permissions(manage_messages=True)
async def purge(
    ctx: commands.Context,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT],
) -> None:
    await _purge_messages(ctx, lambda _: True, limit=count)


@purge.command(name="count", description="Delete a specific number of recent messages.")
@app_commands.describe(count="Number of messages to delete.")
async def purge_count(
    ctx: commands.Context,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT],
) -> None:
    await _purge_messages(
        ctx,
        lambda _: True,
        limit=count,
        result=lambda deleted: f"Purged **{deleted}** messages.",
    )


@purge.command(name="bot", description="Delete recent messages sent by bots.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_bot(
    ctx: commands.Context,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_messages(
        ctx,
        lambda message: message.author.bot,
        limit=DEFAULT_PURGE_LIMIT if count is None else count,
        result=lambda deleted: f"Purged **{deleted}** messages sent by bots.",
    )


@purge.command(name="from", aliases=["user"], description="Delete recent messages from a member.")
@app_commands.describe(user="The member whose messages to delete.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_from(
    ctx: commands.Context,
    user: discord.Member,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_messages(
        ctx,
        lambda message: message.author.id == user.id,
        limit=DEFAULT_PURGE_LIMIT if count is None else count,
        result=lambda deleted: f"Purged **{deleted}** messages from {user}.",
    )


@purge.command(name="mentions", description="Delete recent messages containing mentions.")
@app_commands.describe(user="Optionally match messages from or mentioning this member.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_mentions(
    ctx: commands.Context,
    user: discord.Member | None = None,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    def contains_mention(message: discord.Message) -> bool:
        if not (
            message.mentions
            or message.role_mentions
            or message.mention_everyone
        ):
            return False
        if user is None:
            return True
        return message.author.id == user.id or any(
            mentioned.id == user.id for mentioned in message.mentions
        )

    if user is None:
        result = lambda deleted: (
            f"Purged **{deleted}** messages containing mentions."
        )
    else:
        result = lambda deleted: (
            f"Purged **{deleted}** messages from or mentioning {user}."
        )
    await _purge_messages(
        ctx,
        contains_mention,
        limit=DEFAULT_PURGE_LIMIT if count is None else count,
        result=result,
    )


@purge.command(name="self", aliases=["me"], description="Delete your recent messages.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_self(
    ctx: commands.Context,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_messages(
        ctx,
        lambda message: message.author.id == ctx.author.id,
        limit=DEFAULT_PURGE_LIMIT if count is None else count,
        result=lambda deleted: f"Purged **{deleted}** of your messages.",
    )


@purge.command(name="after", description="Delete recent messages after a message ID.")
@app_commands.describe(message_id="The ID of the boundary message.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_after(
    ctx: commands.Context,
    message_id: str,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_by_message_id(ctx, message_id, after=True, count=count)


@purge.command(name="before", description="Delete recent messages before a message ID.")
@app_commands.describe(message_id="The ID of the boundary message.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_before(
    ctx: commands.Context,
    message_id: str,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_by_message_id(ctx, message_id, after=False, count=count)


async def _purge_by_message_id(
    ctx: commands.Context,
    message_id: str,
    *,
    after: bool,
    count: int | None,
) -> None:
    if count is not None and not await _valid_count(ctx, count):
        return

    channel = ctx.channel
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        await _send_result(ctx, "Messages can't be purged from this channel.")
        return
    try:
        boundary_id = int(message_id)
        if boundary_id <= 0:
            raise ValueError
    except ValueError:
        await _send_result(ctx, "Enter a valid message ID.")
        return

    await _defer(ctx)
    try:
        boundary = await channel.fetch_message(boundary_id)
    except discord.NotFound:
        await _send_result(ctx, "I couldn't find that message in this channel.")
        return
    except discord.HTTPException as error:
        logger.warning(
            "Could not fetch purge boundary message %s in channel %s (HTTP %s).",
            boundary_id,
            channel.id,
            error.status,
        )
        await _send_result(ctx, "Discord couldn't retrieve that message.")
        return

    direction = "after" if after else "before"
    await _purge_messages(
        ctx,
        lambda _: True,
        limit=DEFAULT_PURGE_LIMIT if count is None else count,
        after=boundary if after else None,
        before=None if after else boundary,
        result=lambda deleted: (
            f"Purged **{deleted}** messages {direction} "
            f"[this message]({_message_link(boundary)})."
        ),
    )


async def _purge_matching_content(
    ctx: commands.Context,
    content: str,
    predicate: Callable[[str, str], bool],
    *,
    count: int | None,
    result: Callable[[int, str], str],
) -> None:
    content = content.strip()
    if not content:
        await _send_result(ctx, "Enter the text to match.")
        return
    folded_content = content.casefold()
    await _purge_messages(
        ctx,
        lambda message: predicate(message.content.casefold(), folded_content),
        limit=DEFAULT_PURGE_LIMIT if count is None else count,
        result=lambda deleted: result(deleted, content),
    )


@purge.command(name="contains", description="Delete messages containing text.")
@app_commands.describe(
    content="The text to find in messages (quote it if it contains spaces)."
)
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_contains(
    ctx: commands.Context,
    content: str,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_matching_content(
        ctx,
        content,
        lambda message_content, search: search in message_content,
        count=count,
        result=lambda deleted, search: (
            f'Purged **{deleted}** messages containing "{search}".'
        ),
    )


@purge.command(name="startswith", description="Delete messages starting with text.")
@app_commands.describe(
    content="The text messages must start with (quote it if it contains spaces)."
)
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_startswith(
    ctx: commands.Context,
    content: str,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_matching_content(
        ctx,
        content,
        lambda message_content, search: message_content.startswith(search),
        count=count,
        result=lambda deleted, search: (
            f'Purged **{deleted}** messages starting with "{search}".'
        ),
    )


@purge.command(name="endswith", description="Delete messages ending with text.")
@app_commands.describe(
    content="The text messages must end with (quote it if it contains spaces)."
)
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_endswith(
    ctx: commands.Context,
    content: str,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_matching_content(
        ctx,
        content,
        lambda message_content, search: message_content.endswith(search),
        count=count,
        result=lambda deleted, search: (
            f'Purged **{deleted}** messages ending with "{search}".'
        ),
    )


@purge.command(name="links", aliases=["url", "urls"],description="Delete messages with non-GIF URLs.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_links(
    ctx: commands.Context,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_messages(
        ctx,
        lambda message: any(
            not _is_gif_url(url) for url in _message_urls(message)
        ),
        limit=DEFAULT_PURGE_LIMIT if count is None else count,
        result=lambda deleted: f"Purged **{deleted}** messages containing links.",
    )


@purge.command(name="invites", aliases=["servers"], description="Delete messages containing Discord invites.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_invites(
    ctx: commands.Context,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_messages(
        ctx,
        lambda message: INVITE_PATTERN.search(message.content) is not None,
        limit=DEFAULT_PURGE_LIMIT if count is None else count,
        result=lambda deleted: (
            f"Purged **{deleted}** messages containing Discord invites."
        ),
    )


@purge.command(name="gifs", description="Delete messages containing GIFs.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_gifs(
    ctx: commands.Context,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_messages(
        ctx,
        _message_has_gif,
        limit=DEFAULT_PURGE_LIMIT if count is None else count,
        result=lambda deleted: f"Purged **{deleted}** messages containing GIFs.",
    )


@purge.command(name="stickers", description="Delete messages containing stickers.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_stickers(
    ctx: commands.Context,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_messages(
        ctx,
        lambda message: bool(message.stickers),
        limit=DEFAULT_PURGE_LIMIT if count is None else count,
        result=lambda deleted: (
            f"Purged **{deleted}** messages containing stickers."
        ),
    )


@purge.command(name="attachments", description="Delete messages with attachments.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_attachments(
    ctx: commands.Context,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_messages(
        ctx,
        lambda message: bool(message.attachments),
        limit=DEFAULT_PURGE_LIMIT if count is None else count,
        result=lambda deleted: (
            f"Purged **{deleted}** messages containing attachments."
        ),
    )


@purge.command(name="embeds", description="Delete messages containing embeds.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_embeds(
    ctx: commands.Context,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    await _purge_messages(
        ctx,
        lambda message: bool(message.embeds),
        limit=DEFAULT_PURGE_LIMIT if count is None else count,
        result=lambda deleted: f"Purged **{deleted}** messages containing embeds.",
    )


@purge.command(name="reactions", description="Remove reactions from recent messages.")
@app_commands.describe(count="Maximum number of recent messages to check (default: 100).")
async def purge_reactions(
    ctx: commands.Context,
    count: app_commands.Range[int, 1, MAX_PURGE_LIMIT] | None = None,
) -> None:
    if count is not None and not await _valid_count(ctx, count):
        return

    channel = ctx.channel
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        await _send_result(ctx, "Reactions can't be cleared in this channel.")
        return

    await _defer(ctx)
    command_message_id = getattr(ctx.message, "id", None)
    cleared = 0
    failed = 0
    try:
        async for message in channel.history(
            limit=DEFAULT_PURGE_LIMIT if count is None else count
        ):
            if message.id == command_message_id or not message.reactions:
                continue
            try:
                await message.clear_reactions()
            except discord.HTTPException as error:
                failed += 1
                logger.warning(
                    "Could not clear reactions from message %s in channel %s (HTTP %s).",
                    message.id,
                    channel.id,
                    error.status,
                )
            else:
                cleared += 1
    except discord.HTTPException as error:
        logger.warning(
            "Could not read recent messages in channel %s (HTTP %s).",
            channel.id,
            error.status,
        )
        await _send_result(ctx, "Discord couldn't read recent messages.")
        return

    response = f"Removed reactions from **{cleared}** messages."
    if failed:
        response += f" Failed to clear reactions from {failed} message(s)."
    await _send_result(ctx, response)