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

# bot.extensions.information:userid
#
# Upon running `,userid` without any extra input
# the bot shows the user ID of ctx.author, if
# the user runs `,userid <user.id>` the bot will
# show who that user ID belongs to, if the user
# runs `,userid <@user.id>` the bot will show the
# mentioned user's user ID.
#
# Outputs are as followed:
#
# `,userid` = "Your user ID is `<ctx.author.id>`"
# `,userid <your_user.id>` = "That is your user ID: `<your_user.id>`"
# `,userid <ctx.bot.user.id>` = "That is my user ID: `<ctx.bot.user.id>`"
# `,userid <@ctx.bot.user.id>` = "My user ID is: `<ctx.bot.user.id>`"
# `,userid <user.id>` = "That is <user.name>'s user ID: `<user.id>`"
# `,userid <@user.id>` = "<user.name>'s user ID is: `<user.id>`"
# Multiple IDs or mentions can be provided; each result appears on a new line.


import re

from discord import app_commands
from bot.base.imports import commands, discord

USER_MENTION = re.compile(r"<@!?(\d+)>")


def _find_named_user(
    ctx: commands.Context,
    name: str,
) -> discord.Member | discord.User | None:
    if ctx.guild is not None:
        member = ctx.guild.get_member_named(name)
        if member is not None:
            return member

    normalized_name = name.casefold()
    return discord.utils.find(
        lambda user: (
            user.name.casefold() == normalized_name
            or (user.global_name or "").casefold() == normalized_name
        ),
        ctx.bot.users,
    )


async def _get_user_by_id(
    ctx: commands.Context,
    user_id: int,
) -> discord.Member | discord.User | None:
    if user_id == ctx.author.id:
        return ctx.author

    if ctx.bot.user is not None and user_id == ctx.bot.user.id:
        return ctx.bot.user

    if ctx.guild is not None:
        member = ctx.guild.get_member(user_id)
        if member is not None:
            return member

    message = ctx.message
    if message is not None:
        mentioned_user = discord.utils.get(message.mentions, id=user_id)
        if mentioned_user is not None:
            return mentioned_user

    user = ctx.bot.get_user(user_id)
    if user is not None:
        return user

    try:
        return await ctx.bot.fetch_user(user_id)
    except discord.NotFound:
        return None


def _user_id_response(
    ctx: commands.Context,
    user: discord.Member | discord.User | None,
    user_id: int,
    *,
    is_mention: bool = False,
) -> str:
    if user is None:
        return "User not found."

    if is_mention:
        if ctx.bot.user is not None and user.id == ctx.bot.user.id:
            return f"My user ID is: `{user.id}`"

        return f"**{user.name}**'s user ID is: `{user.id}`"

    if user_id == ctx.author.id:
        return f"That is your user ID: `{user_id}`"

    if ctx.bot.user is not None and user_id == ctx.bot.user.id:
        return f"That is my user ID: `{user_id}`"

    return f"That is **{user.name}**'s user ID: `{user.id}`"


async def _user_id_response_for_input(
    ctx: commands.Context,
    value: str,
) -> tuple[str, int | None]:
    mention = USER_MENTION.fullmatch(value)
    is_mention = mention is not None
    if is_mention:
        assert mention is not None
        value = mention.group(1)

    if value.isdecimal():
        if len(value) > 20:
            return "Invalid user ID.", None

        user_id = int(value)
        user = await _get_user_by_id(ctx, user_id)
        return (
            _user_id_response(ctx, user, user_id, is_mention=is_mention),
            user_id,
        )

    user = _find_named_user(ctx, value)
    if user is None:
        return "User not found. Provide a username, user ID, or mention.", None

    return _user_id_response(ctx, user, user.id), user.id


async def _send_user_id_responses(
    ctx: commands.Context,
    responses: list[str],
) -> None:
    message = ""
    for response in responses:
        next_message = f"{message}\n{response}" if message else response
        if len(next_message) > 2000:
            await ctx.send(message, allowed_mentions=discord.AllowedMentions.none())
            message = response
        else:
            message = next_message

    if message:
        await ctx.send(message, allowed_mentions=discord.AllowedMentions.none())


@commands.hybrid_command(name="userid", aliases=("uid", "whoid", "id"))
@app_commands.describe(user_id="The ID, mention, or name of the user to look up.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def userid(
    ctx: commands.Context,
    *,
    user_id: str | None = None,
) -> None:
    if not user_id:
        await ctx.send(f"Your user ID is `{ctx.author.id}`")
        return

    values = user_id.split()
    if len(values) > 1 and _find_named_user(ctx, user_id) is not None:
        values = [user_id]

    responses: list[str] = []
    seen_user_ids: set[int] = set()
    for value in values:
        response, resolved_user_id = await _user_id_response_for_input(ctx, value)
        if resolved_user_id is not None:
            if resolved_user_id in seen_user_ids:
                continue
            seen_user_ids.add(resolved_user_id)
        responses.append(response)

    await _send_user_id_responses(ctx, responses)
