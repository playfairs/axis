import asyncio
import io

from discord import app_commands
from PIL import Image, ImageSequence, UnidentifiedImageError

from bot.base.imports import commands, discord


def _gif_frame(frame: Image.Image) -> Image.Image:
    rgba = frame.convert("RGBA")
    alpha = rgba.getchannel("A")
    has_transparency = alpha.getextrema()[0] < 255
    colors = 255 if has_transparency else 256
    indexed = rgba.convert("RGB").quantize(
        colors=colors,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.FLOYDSTEINBERG,
    )
    if has_transparency:
        palette = indexed.getpalette()
        indexed = indexed.point(lambda color: color + 1)
        indexed.putpalette([0, 0, 0, *palette[:765]])
        transparent = alpha.point(lambda value: 255 if value < 128 else 0)
        indexed.paste(0, mask=transparent)
        indexed.info["transparency"] = 0
    return indexed


def _convert_to_gif(image_data: bytes) -> bytes:
    with Image.open(io.BytesIO(image_data)) as source:
        if Image.MAX_IMAGE_PIXELS is not None:
            if source.width * source.height > Image.MAX_IMAGE_PIXELS:
                raise Image.DecompressionBombError(
                    "The image exceeds Pillow's decompression pixel limit."
                )
        loop = source.info.get("loop", 0)
        frames = []
        durations = []
        for frame in ImageSequence.Iterator(source):
            frames.append(_gif_frame(frame))
            durations.append(frame.info.get("duration", 100))

        output = io.BytesIO()
        frames[0].save(
            output,
            format="GIF",
            save_all=len(frames) > 1,
            append_images=frames[1:],
            duration=durations if len(frames) > 1 else durations[0],
            loop=loop,
            disposal=2,
            optimize=False,
        )
    return output.getvalue()


async def _find_attachment(ctx: commands.Context) -> discord.Attachment | None:
    if ctx.message.attachments:
        return ctx.message.attachments[0]

    reference = ctx.message.reference
    if reference is None or reference.message_id is None:
        return None

    referenced_message = reference.resolved
    if not isinstance(referenced_message, discord.Message):
        referenced_message = await ctx.channel.fetch_message(reference.message_id)
    if referenced_message.attachments:
        return referenced_message.attachments[0]
    return None


@commands.hybrid_command(name="gif", description="Convert an image to a GIF.")
@app_commands.describe(
    image="The image to convert, or reply to a message with an image."
)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def gif(
    ctx: commands.Context,
    image: discord.Attachment | None = None,
) -> None:
    attachment = image or await _find_attachment(ctx)
    if attachment is None:
        await ctx.send(
            "Attach an image, reply to a message with an image, "
            "or select an image in the `/gif` command."
        )
        return

    try:
        image_data = await attachment.read()
        gif_data = await asyncio.to_thread(_convert_to_gif, image_data)
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError):
        await ctx.send("That attachment isn't a supported image.")
        return

    await ctx.send(
        file=discord.File(io.BytesIO(gif_data), filename="converted.gif"),
    )