import discord

from bot.base.imports import commands, logger
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


@commands.group(name="channel", invoke_without_command=True)
async def channel(ctx: commands.Context) -> None:
    await ctx.invoke(help_command, command_name="channel")


@channel.command(name="create", aliases=["new"])
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


@channel.command(name="rename")
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


@channel.command(name="delete")
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
