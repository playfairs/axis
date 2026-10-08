import colorsys
import random

import aiohttp
from discord import app_commands

from bot.base.imports import commands, discord


@commands.hybrid_command(
    name="color",
    aliases=("hex", "colour"),
    description="Shows a color swatch and RGB, HEX, HSL info.",
)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(hexcode="The hex code to show.")
async def color(ctx: commands.Context, hexcode: str | None = None) -> None:
    """Shows a color swatch and RGB, HEX, HSL info."""
    if not hexcode:
        hexcode = f"{random.randint(0, 0xFFFFFF):06x}"
    else:
        hexcode = hexcode.lower().replace("#", "").strip()
        if len(hexcode) not in (3, 6) or not all(
            char in "0123456789abcdef" for char in hexcode
        ):
            await ctx.send(
                "Not a valid hex code. Hex codes work A-F and 0-9",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

    if len(hexcode) == 3:
        hexcode = "".join(char * 2 for char in hexcode)

    hex_val = hexcode.lower()
    rgb = tuple(int(hex_val[i : i + 2], 16) for i in range(0, 6, 2))

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://www.thecolorapi.com/id?hex={hex_val}&format=json",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    color_name = data.get("name", {}).get("value", "")
                    color_display = (
                        f"{color_name.title()} (`#{hex_val.upper()}`)"
                        if color_name
                        else f"`#{hex_val.upper()}`"
                    )
                    cmyk = (
                        data.get("cmyk", {})
                        .get("value", "")
                        .replace("cmyk(", "")
                        .rstrip(")")
                    )
                    hsv = (
                        data.get("hsv", {})
                        .get("value", "")
                        .replace("hsv(", "")
                        .rstrip(")")
                    )
                    xyz = (
                        data.get("XYZ", {})
                        .get("value", "")
                        .replace("XYZ(", "")
                        .rstrip(")")
                    )
                else:
                    color_display = f"`#{hex_val.upper()}`"
                    cmyk = hsv = xyz = "N/A"

        h, l, s = colorsys.rgb_to_hls(
            rgb[0] / 255,
            rgb[1] / 255,
            rgb[2] / 255,
        )
        hsl = (round(h * 360), round(s * 100), round(l * 100))
    except Exception as error:
        await ctx.send(
            f"Error in color command: {error}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    url = f"https://singlecolorimage.com/get/{hex_val}/600x100"
    container = discord.ui.Container(
        discord.ui.TextDisplay(content=f"### Color #{hex_val.upper()}"),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay(
            content=(
                f"**Name:** {color_display}\n"
                f"**RGB:** `{rgb}`\n"
                f"**HSL:** `{hsl}`\n"
                f"**CMYK:** `{cmyk}`\n"
                f"**HSV:** `{hsv}`\n"
                f"**XYZ:** `{xyz}`"
            )
        ),
        accent_color=discord.Color(int(f"0x{hex_val}", 16)),
    )
    container.add_item(
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small)
    )
    container.add_item(
        discord.ui.MediaGallery(discord.MediaGalleryItem(media=url))
    )

    view = discord.ui.LayoutView()
    view.add_item(container)
    await ctx.send(view=view, allowed_mentions=discord.AllowedMentions.none())

