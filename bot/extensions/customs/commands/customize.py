import base64
from typing import Any

from bot.base.imports import commands, discord
from bot.extensions.customs import repository, service
from bot.extensions.customs.styles import (
    EFFECT_STYLES,
    FONT_STYLES,
    format_colors,
    parse_hex_color,
    style_name,
)


def _customization_options(
    styles: tuple[tuple[int, str], ...],
    current: Any,
) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=f"{name} (ID {style_id})",
            value=str(style_id),
            default=current == style_id,
        )
        for style_id, name in styles
    ]


def _profile_embed(profile: dict[str, Any]) -> discord.Embed:
    display_name = profile.get("display_name") or "Default bot name"
    bio = profile.get("bio") or "Not set"
    embed = discord.Embed(
        title="Server-specific bot profile",
        description=(
            f"Display name: **{discord.utils.escape_markdown(str(display_name))}**"
        ),
    )
    embed.add_field(
        name="Avatar",
        value="Custom" if profile.get("avatar") else "Default",
        inline=True,
    )
    embed.add_field(
        name="Banner",
        value="Custom" if profile.get("banner") else "Default",
        inline=True,
    )
    embed.add_field(
        name="Bio",
        value=discord.utils.escape_markdown(str(bio))[:1024],
        inline=False,
    )
    embed.add_field(
        name="Font",
        value=style_name(FONT_STYLES, profile.get("display_name_font_id")),
        inline=True,
    )
    embed.add_field(
        name="Effect",
        value=style_name(EFFECT_STYLES, profile.get("display_name_effect_id")),
        inline=True,
    )
    embed.add_field(
        name="Colors",
        value=format_colors(profile.get("display_name_colors")),
        inline=True,
    )
    embed.add_field(
        name="Available fonts",
        value=", ".join(
            f"{name} ({style_id})" for style_id, name in FONT_STYLES
        ),
        inline=False,
    )
    embed.add_field(
        name="Available effects",
        value=", ".join(
            f"{name} ({style_id})" for style_id, name in EFFECT_STYLES
        ),
        inline=False,
    )
    embed.set_footer(
        text=(
            "Select a font or effect below. Discord may reject styles unavailable "
            "to this bot or server."
        )
    )
    return embed


async def _send_http_error(
    destination: commands.Context | discord.Interaction,
    error: discord.HTTPException | discord.RateLimited,
) -> None:
    message = service.discord_error_message(error)[:500]
    if isinstance(destination, discord.Interaction):
        await destination.followup.send(
            message,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    else:
        await destination.send(
            message,
            allowed_mentions=discord.AllowedMentions.none(),
        )


class _StyleSelect(discord.ui.Select):
    def __init__(
        self,
        guild_id: int,
        profile: dict[str, Any],
        *,
        field: str,
        styles: tuple[tuple[int, str], ...],
    ) -> None:
        self.guild_id = guild_id
        self.field = field
        super().__init__(
            placeholder=f"Choose a {_style_kind(field)}",
            min_values=1,
            max_values=1,
            options=_customization_options(styles, profile.get(field)),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != self.guild_id:
            await interaction.response.send_message(
                "This style menu can only be used in its original server.",
                ephemeral=True,
            )
            return
        await interaction.response.defer()
        try:
            style_id = int(self.values[0])
            profile = await service.apply_customization(
                interaction.client,
                self.guild_id,
                {self.field: style_id},
            )
        except service.GuildNotWhitelisted:
            await interaction.followup.send(
                "Customization access has been revoked for this server.",
                ephemeral=True,
            )
            return
        except (discord.HTTPException, discord.RateLimited) as error:
            await _send_http_error(interaction, error)
            return

        await interaction.edit_original_response(
            embed=_profile_embed(profile),
            view=_DisplayNameView(self.guild_id, profile),
        )


def _style_kind(field: str) -> str:
    return "font" if field == "display_name_font_id" else "effect"


class _DisplayNameView(discord.ui.View):
    def __init__(self, guild_id: int, profile: dict[str, Any]) -> None:
        super().__init__(timeout=300)
        self.add_item(
            _StyleSelect(
                guild_id,
                profile,
                field="display_name_font_id",
                styles=FONT_STYLES,
            )
        )
        self.add_item(
            _StyleSelect(
                guild_id,
                profile,
                field="display_name_effect_id",
                styles=EFFECT_STYLES,
            )
        )


async def _require_whitelist(ctx: commands.Context) -> bool:
    if ctx.guild is None:
        return False
    if not await repository.is_whitelisted(ctx.bot, ctx.guild.id):
        await ctx.send(
            "This server is not whitelisted for customization by the bot owner."
        )
        return False
    return True


@commands.hybrid_group(
    name="customize",
    invoke_without_command=True,
    description="Customize this server's bot profile.",
)
@commands.guild_only()
@commands.check(_require_whitelist)
async def customize(ctx: commands.Context) -> None:
    await ctx.send_help(ctx.command)


async def _customize_image(
    ctx: commands.Context,
    field: str,
    attachment: discord.Attachment | None,
) -> None:
    if ctx.guild is None:
        return
    if attachment is not None:
        content_type = attachment.content_type
        if content_type is None or not content_type.startswith("image/"):
            await ctx.send("Attach a supported image file.")
            return
    try:
        if attachment is None:
            data = None
        else:
            media_type = content_type.split(";", 1)[0].strip().lower()
            image = await attachment.read()
            data = f"data:{media_type};base64,{base64.b64encode(image).decode('ascii')}"
        await service.apply_customization(
            ctx.bot,
            ctx.guild.id,
            {field: data},
        )
    except service.GuildNotWhitelisted:
        await ctx.send("Customization access has been revoked for this server.")
    except (discord.HTTPException, discord.RateLimited) as error:
        await _send_http_error(ctx, error)
    else:
        state = "reset" if attachment is None else "updated"
        await ctx.send(f"The server-specific {field} was {state}.")


@customize.command(
    name="avatar",
    description="Set a server-specific avatar; omit the attachment to reset it.",
)
async def customize_avatar(
    ctx: commands.Context,
    attachment: discord.Attachment | None = None,
) -> None:
    await _customize_image(ctx, "avatar", attachment)


@customize.command(
    name="banner",
    description="Set a server-specific banner; omit the attachment to reset it.",
)
async def customize_banner(
    ctx: commands.Context,
    attachment: discord.Attachment | None = None,
) -> None:
    await _customize_image(ctx, "banner", attachment)


@customize.command(
    name="bio",
    description="Set a server-specific bio; omit text to reset it.",
)
async def customize_bio(
    ctx: commands.Context,
    *,
    bio: str | None = None,
) -> None:
    if ctx.guild is None:
        return
    if bio is not None and len(bio) > 190:
        await ctx.send("The server-specific bio cannot exceed 190 characters.")
        return
    try:
        await service.apply_customization(
            ctx.bot,
            ctx.guild.id,
            {"bio": bio},
        )
    except service.GuildNotWhitelisted:
        await ctx.send("Customization access has been revoked for this server.")
    except (discord.HTTPException, discord.RateLimited) as error:
        await _send_http_error(ctx, error)
    else:
        await ctx.send(
            "The server-specific bio was reset."
            if bio is None
            else "The server-specific bio was updated."
        )


@customize.group(
    name="displayname",
    fallback="show",
    invoke_without_command=True,
    description="Set the server display name and its native Discord style.",
)
async def customize_displayname(
    ctx: commands.Context,
    *,
    display_name: str | None = None,
) -> None:
    if ctx.guild is None:
        return
    if display_name is not None:
        if not 1 <= len(display_name) <= 32:
            await ctx.send("The server display name must be 1-32 characters.")
            return
        try:
            await service.apply_customization(
                ctx.bot,
                ctx.guild.id,
                {"nick": display_name},
            )
        except service.GuildNotWhitelisted:
            await ctx.send("Customization access has been revoked for this server.")
        except (discord.HTTPException, discord.RateLimited) as error:
            await _send_http_error(ctx, error)
        else:
            await ctx.send("The server-specific display name was updated.")
        return
    try:
        profile = await service.fetch_profile(ctx.bot, ctx.guild.id)
    except (discord.HTTPException, discord.RateLimited) as error:
        await _send_http_error(ctx, error)
        return
    await ctx.send(
        embed=_profile_embed(profile),
        view=_DisplayNameView(ctx.guild.id, profile),
        allowed_mentions=discord.AllowedMentions.none(),
    )


@customize_displayname.command(
    name="color",
    description="Set hex colors supported by the selected display-name effect.",
)
async def customize_displayname_color(
    ctx: commands.Context,
    *,
    colors: str,
) -> None:
    if ctx.guild is None:
        return
    values = colors.replace(",", " ").split()
    if not 1 <= len(values) <= 5:
        await ctx.send("Provide one to five six-digit hex colors.")
        return
    parsed = [parse_hex_color(value) for value in values]
    if any(value is None for value in parsed):
        await ctx.send("Colors must use six-digit hex, such as `#12ABEF`.")
        return
    try:
        await service.apply_display_name_colors(
            ctx.bot,
            ctx.guild.id,
            [value for value in parsed if value is not None],
        )
    except service.GuildNotWhitelisted:
        await ctx.send("Customization access has been revoked for this server.")
    except service.UnsupportedStyleCombination as error:
        await ctx.send(str(error))
    except (discord.HTTPException, discord.RateLimited) as error:
        await _send_http_error(ctx, error)
    else:
        await ctx.send("Display-name colors were updated.")


@customize_displayname.command(
    name="reset",
    description="Reset a display-name property or the entire style.",
)
async def customize_displayname_reset(
    ctx: commands.Context,
    property: str,
) -> None:
    if ctx.guild is None:
        return
    reset_fields: dict[str, dict[str, Any]] = {
        "name": {"nick": None},
        "font": {"display_name_font_id": None},
        "effect": {"display_name_effect_id": None},
        "colors": {"display_name_colors": None},
        "style": {
            "display_name_font_id": None,
            "display_name_effect_id": None,
            "display_name_colors": None,
        },
        "all": {
            "nick": None,
            "display_name_font_id": None,
            "display_name_effect_id": None,
            "display_name_colors": None,
        },
    }
    changes = reset_fields.get(property.casefold())
    if changes is None:
        await ctx.send(
            "Choose `name`, `font`, `effect`, `colors`, `style`, or `all`."
        )
        return
    try:
        await service.apply_customization(ctx.bot, ctx.guild.id, changes)
    except service.GuildNotWhitelisted:
        await ctx.send("Customization access has been revoked for this server.")
    except (discord.HTTPException, discord.RateLimited) as error:
        await _send_http_error(ctx, error)
    else:
        await ctx.send(
            f"The display-name {property.casefold()} customization was reset."
        )
