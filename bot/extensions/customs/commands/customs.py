from typing import Any

from bot.base.imports import commands, discord
from bot.extensions.customs import repository, service
from bot.extensions.customs.styles import (
    EFFECT_STYLES,
    FONT_STYLES,
    format_colors,
    style_name,
)


def _parse_guild_id(value: str) -> int | None:
    if not value.isascii() or not value.isdigit():
        return None
    guild_id = int(value)
    if not 0 < guild_id < (1 << 63):
        return None
    return guild_id


def _configuration_text(config: dict[str, Any]) -> str:
    display_name = config.get("display_name") or "Default"
    bio = config.get("bio") or "Not set"
    return (
        f"Display name: {display_name}\n"
        f"Avatar: {'Custom' if config.get('avatar') else 'Default'}\n"
        f"Banner: {'Custom' if config.get('banner') else 'Default'}\n"
        f"Bio: {bio}\n"
        f"Font: {style_name(FONT_STYLES, config.get('display_name_font_id'))}\n"
        "Effect: "
        f"{style_name(EFFECT_STYLES, config.get('display_name_effect_id'))}\n"
        f"Colors: {format_colors(config.get('display_name_colors'))}"
    )


async def _fetch_guild(
    ctx: commands.Context,
    guild_id: int,
) -> discord.Guild | None:
    try:
        return ctx.bot.get_guild(guild_id) or await ctx.bot.fetch_guild(guild_id)
    except discord.NotFound:
        await ctx.send(
            "Discord could not find that server, or the bot is not a member of it."
        )
    except discord.Forbidden:
        await ctx.send("The bot cannot access that server.")
    except (discord.HTTPException, discord.RateLimited) as error:
        await ctx.send(
            "Could not validate that server: "
            f"{service.discord_error_message(error)[:500]}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
    return None


@commands.hybrid_group(
    name="customs",
    invoke_without_command=True,
    description="Manage the bot's server customization whitelist.",
)
@commands.is_owner()
async def customs(ctx: commands.Context) -> None:
    await ctx.send_help(ctx.command)


@customs.command(
    name="whitelist",
    description="Grant a server access to customization commands.",
)
async def customs_whitelist(ctx: commands.Context, guild_id: str) -> None:
    parsed_id = _parse_guild_id(guild_id)
    if parsed_id is None:
        await ctx.send("Provide a valid Discord server ID.")
        return
    guild = await _fetch_guild(ctx, parsed_id)
    if guild is None:
        return
    if not await service.whitelist_guild(ctx.bot, parsed_id):
        name = discord.utils.escape_markdown(guild.name)
        await ctx.send(
            f"**{name}** (`{parsed_id}`) is already whitelisted.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return
    name = discord.utils.escape_markdown(guild.name)
    await ctx.send(
        f"Whitelisted **{name}** (`{parsed_id}`).",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@customs.command(
    name="blacklist",
    description="Revoke a server's access and reset its customizations.",
)
async def customs_blacklist(ctx: commands.Context, guild_id: str) -> None:
    parsed_id = _parse_guild_id(guild_id)
    if parsed_id is None:
        await ctx.send("Provide a valid Discord server ID.")
        return
    try:
        await service.reset_customizations(
            ctx.bot,
            parsed_id,
            revoke_access=True,
        )
    except (discord.HTTPException, discord.RateLimited) as error:
        await ctx.send(
            "Customization access was revoked, but Discord could not reset the "
            f"server profile: {service.discord_error_message(error)[:500]}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return
    await ctx.send(
        f"Blacklisted `{parsed_id}` and reset all confirmed server-specific "
        "customizations."
    )


@customs.command(
    name="check",
    description="Show a server's whitelist status and customization configuration.",
)
async def customs_check(ctx: commands.Context, guild_id: str) -> None:
    parsed_id = _parse_guild_id(guild_id)
    if parsed_id is None:
        await ctx.send("Provide a valid Discord server ID.")
        return
    record = await repository.get_guild_record(ctx.bot, parsed_id)
    if record is None:
        state = "Unregistered"
        config: dict[str, Any] = {}
    else:
        state = "Whitelisted" if record["whitelisted"] else "Blacklisted"
        config = record["customizations"]
    try:
        config = await service.fetch_profile(ctx.bot, parsed_id)
        if record is not None:
            await repository.save_customizations(ctx.bot, parsed_id, config)
    except (discord.HTTPException, discord.RateLimited) as error:
        await ctx.send(
            "Live profile lookup failed: "
            f"{service.discord_error_message(error)[:500]} Showing the "
            "last confirmed saved configuration.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
    embed = discord.Embed(
        title=f"Server {parsed_id}",
        description=f"Customization access: **{state}**",
    )
    embed.add_field(
        name="Current customization configuration",
        value=discord.utils.escape_markdown(_configuration_text(config))[:1024],
        inline=False,
    )
    await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())


@customs.command(
    name="list",
    description="List all currently whitelisted servers.",
)
async def customs_list(ctx: commands.Context) -> None:
    pool = getattr(ctx.bot, "database_pool", None)
    if pool is None:
        raise RuntimeError("The database pool is not initialized.")
    guild_ids = await pool.fetch(
        """
        SELECT guild_id
        FROM customs_guilds
        WHERE whitelisted = TRUE
        ORDER BY guild_id
        """
    )
    if not guild_ids:
        await ctx.send("No servers are currently whitelisted.")
        return
    lines = []
    for record in guild_ids:
        guild_id = record["guild_id"]
        guild = ctx.bot.get_guild(guild_id)
        name = discord.utils.escape_markdown(guild.name) if guild else "Unknown server"
        lines.append(f"**{name}** — `{guild_id}`")
    chunk = ""
    for line in lines:
        if chunk and len(chunk) + len(line) + 1 > 1900:
            await ctx.send(
                chunk,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            chunk = ""
        chunk = f"{chunk}\n{line}" if chunk else line
    if chunk:
        await ctx.send(
            chunk,
            allowed_mentions=discord.AllowedMentions.none(),
        )


@customs.command(
    name="reset",
    description="Reset a server's customizations without changing whitelist status.",
)
async def customs_reset(ctx: commands.Context, guild_id: str) -> None:
    parsed_id = _parse_guild_id(guild_id)
    if parsed_id is None:
        await ctx.send("Provide a valid Discord server ID.")
        return
    try:
        await service.reset_customizations(ctx.bot, parsed_id)
    except (discord.HTTPException, discord.RateLimited) as error:
        await ctx.send(
            "Discord could not reset this server profile: "
            f"{service.discord_error_message(error)[:500]}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return
    await ctx.send(
        f"Reset all confirmed server-specific customizations for `{parsed_id}`. "
        "Whitelist status was unchanged."
    )
