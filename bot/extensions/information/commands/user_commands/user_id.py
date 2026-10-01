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
        lambda user: user.name.casefold() == normalized_name
        or (user.global_name or "").casefold() == normalized_name,
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


async def _send_user_id(
    ctx: commands.Context,
    user: discord.Member | discord.User | None,
    user_id: int,
) -> None:
    if user_id == ctx.author.id:
        await ctx.send(f"That is your user ID: `{user_id}`")
        return

    if ctx.bot.user is not None and user_id == ctx.bot.user.id:
        await ctx.send(f"That is my user ID: `{user_id}`")
        return

    if user is None:
        await ctx.send("User not found.")
        return

    await ctx.send(
        f"**{user.name}**'s user ID is: `{user.id}`",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@commands.hybrid_command(name="userid", aliases=("uid", "whoid", "id"))
@app_commands.describe(user_id="The ID, mention, or name of the user to look up.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def userid(
    ctx: commands.Context,
    user_id: str | None = None,
) -> None:
    if not user_id:
        await ctx.send(f"Your user ID is `{ctx.author.id}`")
        return

    mention = USER_MENTION.fullmatch(user_id)
    if mention is not None:
        if len(mention.group(1)) > 20:
            await ctx.send("Invalid user ID.")
            return

        target_id = int(mention.group(1))
        user = await _get_user_by_id(ctx, target_id)
        await _send_user_id(ctx, user, target_id)
        return

    if user_id.isdecimal():
        if len(user_id) > 20:
            await ctx.send("Invalid user ID.")
            return

        target_id = int(user_id)
        user = await _get_user_by_id(ctx, target_id)
        await _send_user_id(ctx, user, target_id)
        return

    user = _find_named_user(ctx, user_id)
    if user is None:
        await ctx.send("User not found. Provide a username, user ID, or mention.")
        return

    await _send_user_id(ctx, user, user.id)