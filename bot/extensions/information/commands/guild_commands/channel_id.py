# This file is part of Axis.
#
# Copyright (c) 2026 playfairs
#
# This work is released into the public domain under the Unlicense.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# See the UNLICENSE file for details.


import re

from bot.base.imports import commands, discord

CHANNEL_MENTION = re.compile(r"<#(\d+)>")


@commands.command(name="channelid", aliases=("cid",))
async def channel_id(
    ctx: commands.Context,
    channel_id: str | None = None,
) -> None:
    """Show a channel ID or look up a channel by ID or mention."""
    if channel_id is None:
        await ctx.send(f"This channel's ID is: `{ctx.channel.id}`")
        return

    mention = CHANNEL_MENTION.fullmatch(channel_id)
    is_mention = mention is not None
    if is_mention:
        assert mention is not None
        channel_id = mention.group(1)
    elif not channel_id.isdecimal():
        await ctx.send("Provide a channel ID or channel mention.")
        return

    if len(channel_id) > 20:
        await ctx.send("Invalid channel ID.")
        return

    target_id = int(channel_id)
    if is_mention and target_id == ctx.channel.id:
        await ctx.send(f"That is this channel's channel ID: `{target_id}`")
        return

    if is_mention:
        await ctx.send(f"That channel's ID is: `{target_id}`")
        return

    target_channel = ctx.guild.get_channel_or_thread(target_id) if ctx.guild else None
    if target_channel is None:
        target_channel = ctx.bot.get_channel(target_id)

    if target_channel is None:
        try:
            target_channel = await ctx.bot.fetch_channel(target_id)
        except discord.NotFound:
            await ctx.send("Channel not found.")
            return

    await ctx.send(
        f"That is **{target_channel}**'s channel ID: `{target_id}`",
        allowed_mentions=discord.AllowedMentions.none(),
    )
