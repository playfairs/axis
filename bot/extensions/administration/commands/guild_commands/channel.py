import discord

from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, logger
from bot.core.client.help import help_command


def _parse_channel_id(value: str) -> int | None:
    value = value.strip()
    if value.startswith("<#") and value.endswith(">"):
        value = value[2:-1]
    if not value.isdecimal():
        return None
    return int(value)


async def _resolve_channel(
    ctx: commands.Context,
    value: str,
) -> discord.abc.GuildChannel | None:
    if ctx.guild is None:
        return None
    channel_id = _parse_channel_id(value)
    if channel_id is None:
        return None

    target = ctx.guild.get_channel(channel_id)
    if target is None:
        fetched = await ctx.bot.fetch_channel(channel_id)
        if isinstance(fetched, discord.abc.GuildChannel):
            target = fetched
    return target


@commands.group(
    name="channel",
    invoke_without_command=True,
    description="Create, rename, and delete server channels.",
)
async def channel(ctx: commands.Context) -> None:
    await ctx.invoke(help_command, command_name="channel")


class ChannelInfoView(discord.ui.LayoutView):
    def __init__(self, channel: discord.abc.GuildChannel) -> None:
        super().__init__()
        channel_type = channel.__class__.__name__.replace("Channel", "").replace(
            "Thread", "Thread"
        )
        if isinstance(channel, discord.CategoryChannel):
            channel_type = "Category"
        elif isinstance(channel, discord.ForumChannel):
            channel_type = "Forum"
        elif isinstance(channel, discord.TextChannel):
            channel_type = "Text"
        elif isinstance(channel, discord.VoiceChannel):
            channel_type = "Voice"
        elif isinstance(channel, discord.StageChannel):
            channel_type = "Stage"
        elif isinstance(channel, discord.Thread):
            channel_type = "Thread"

        details_lines = [
            f"**ID:** `{channel.id}`",
            f"**Type:** {channel_type}",
            f"**Mention:** {channel.mention}",
            f"**Created:** <t:{int(channel.created_at.timestamp())}:F> "
            f"(<t:{int(channel.created_at.timestamp())}:R>)",
            f"**Position:** {channel.position}",
            f"**Category:** {channel.category.mention if channel.category else 'None'}",
        ]
        if isinstance(channel, discord.TextChannel):
            details_lines.extend(
                [
                    f"**Topic:** {channel.topic or 'None'}",
                    f"**Slowmode:** {channel.slowmode_delay}s",
                    f"**NSFW:** {'Yes' if channel.nsfw else 'No'}",
                    f"**Members:** {len(channel.members)}",
                ]
            )
        elif isinstance(channel, discord.VoiceChannel):
            details_lines.extend(
                [
                    f"**Bitrate:** {channel.bitrate}bps",
                    f"**Member limit:** {channel.user_limit or 'Unlimited'}",
                    f"**RTC region:** {channel.rtc_region or 'Automatic'}",
                    f"**Members:** {len(channel.members)}",
                ]
            )
        elif isinstance(channel, discord.StageChannel):
            details_lines.extend(
                [
                    f"**Bitrate:** {channel.bitrate}bps",
                    f"**Member limit:** {channel.user_limit or 'Unlimited'}",
                    f"**Region:** {channel.rtc_region or 'Automatic'}",
                    f"**Members:** {len(channel.members)}",
                ]
            )
        elif isinstance(channel, discord.ForumChannel):
            details_lines.extend(
                [
                    f"**NSFW:** {'Yes' if channel.nsfw else 'No'}",
                    f"**Default reaction:** {channel.default_reaction_emoji or 'None'}",
                    f"**Archive duration:** {channel.default_auto_archive_duration}",
                ]
            )
        elif isinstance(channel, discord.Thread):
            details_lines.extend(
                [
                    f"**Parent:** {channel.parent.mention if channel.parent else 'None'}",
                    f"**Archived:** {'Yes' if channel.archived else 'No'}",
                    f"**Locked:** {'Yes' if channel.locked else 'No'}",
                    f"**Members:** {len(channel.members) if hasattr(channel, 'members') else 'N/A'}",
                ]
            )

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## #{channel.name}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay("\n".join(details_lines)),
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )


@channel.command(
    name="info",
    aliases=("details",),
    description="Show detailed information about a channel.",
)
@commands.guild_only()
async def channel_info(
    ctx: commands.Context,
    target: str | None = None,
) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    resolved = ctx.channel if target is None else await _resolve_channel(ctx, target)
    if resolved is None:
        await ctx.send("Couldn't find that channel. Use a channel mention or ID.")
        return
    if resolved.guild != ctx.guild:
        await ctx.send("That channel isn't in this server.")
        return

    await ctx.send(
        view=ChannelInfoView(resolved),
        allowed_mentions=discord.AllowedMentions.none(),
    )


@channel.command(
    name="create",
    aliases=["new"],
    description="Create a text channel, optionally inside a category.",
)
@commands.has_guild_permissions(manage_channels=True)
@commands.bot_has_guild_permissions(manage_channels=True)
async def channel_create(
    ctx: commands.Context,
    name: str = "new-channel",
    category_id: str | None = None,
) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    name = name.strip()
    if not name or len(name) > 100:
        await ctx.send("Channel names must be between 1 and 100 characters.")
        return

    category: discord.CategoryChannel | None = None
    if category_id is not None:
        try:
            resolved_category = await _resolve_channel(ctx, category_id)
        except discord.HTTPException as error:
            logger.warning(
                "Could not resolve category {} in guild {} ({}).",
                category_id,
                ctx.guild.id,
                type(error).__name__,
            )
            await ctx.send("Couldn't find that category.")
            return
        if not isinstance(resolved_category, discord.CategoryChannel):
            await ctx.send("That category wasn't found in this server.")
            return
        if resolved_category.guild != ctx.guild:
            await ctx.send("That category isn't in this server.")
            return
        category = resolved_category

    try:
        created = await ctx.guild.create_text_channel(
            name,
            category=category,
            reason=f"Created by {ctx.author} via channel command",
        )
    except discord.HTTPException as error:
        logger.warning(
            "Could not create a channel in guild {} ({}).",
            ctx.guild.id,
            type(error).__name__,
        )
        await ctx.send("Couldn't create that channel. Check the name and permissions.")
        return

    await ctx.send(f"Created {created.mention}.")


@channel.command(
    name="rename",
    description="Rename this channel or another channel by ID or mention.",
)
@commands.has_guild_permissions(manage_channels=True)
@commands.bot_has_guild_permissions(manage_channels=True)
async def channel_rename(
    ctx: commands.Context,
    target_or_name: str,
    new_name: str | None = None,
) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    if new_name is None:
        target = ctx.channel
        name = target_or_name
        if not isinstance(target, discord.abc.GuildChannel):
            await ctx.send("This command must be run in a channel that can be renamed.")
            return
    else:
        name = new_name
        try:
            target = await _resolve_channel(ctx, target_or_name)
        except discord.HTTPException as error:
            logger.warning(
                "Could not resolve channel {} in guild {} ({}).",
                target_or_name,
                ctx.guild.id,
                type(error).__name__,
            )
            await ctx.send("Couldn't find that channel.")
            return
        if target is None:
            await ctx.send("Couldn't find that channel. Use a channel mention or ID.")
            return
        if target.guild != ctx.guild:
            await ctx.send("That channel isn't in this server.")
            return

    name = name.strip()
    if not name or len(name) > 100:
        await ctx.send("Channel names must be between 1 and 100 characters.")
        return

    old_name = target.name
    try:
        await target.edit(
            name=name,
            reason=f"Renamed by {ctx.author} via channel command",
        )
    except discord.HTTPException as error:
        logger.warning(
            "Could not rename channel {} in guild {} ({}).",
            target.id,
            ctx.guild.id,
            type(error).__name__,
        )
        await ctx.send("Couldn't rename that channel. Check the name and permissions.")
        return

    await ctx.send(f"Renamed **{old_name}** to **{target.name}**.")


@channel.command(
    name="delete",
    description="Delete this channel or another channel by ID or mention.",
)
@commands.has_guild_permissions(manage_channels=True)
@commands.bot_has_guild_permissions(manage_channels=True)
async def channel_delete(
    ctx: commands.Context,
    target_id: str | None = None,
) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    if target_id is None:
        target = ctx.channel
        if not isinstance(target, discord.abc.GuildChannel):
            await ctx.send("This command must be run in a channel that can be deleted.")
            return
    else:
        try:
            target = await _resolve_channel(ctx, target_id)
        except discord.HTTPException as error:
            logger.warning(
                "Could not resolve channel {} in guild {} ({}).",
                target_id,
                ctx.guild.id,
                type(error).__name__,
            )
            await ctx.send("Couldn't find that channel.")
            return
        if target is None:
            await ctx.send("Couldn't find that channel. Use a channel mention or ID.")
            return
    if target.guild != ctx.guild:
        await ctx.send("That channel isn't in this server.")
        return

    channel_name = target.name
    deleting_current_channel = target.id == ctx.channel.id
    if deleting_current_channel:
        await ctx.send(f"Deleting **{channel_name}**...")
    try:
        await target.delete(
            reason=f"Deleted by {ctx.author} via channel command",
        )
    except discord.HTTPException as error:
        logger.warning(
            "Could not delete channel {} in guild {} ({}).",
            target.id,
            ctx.guild.id,
            type(error).__name__,
        )
        await ctx.send("Couldn't delete that channel. Check the permissions.")
        return

    if not deleting_current_channel:
        await ctx.send(f"Deleted **{channel_name}**.")
