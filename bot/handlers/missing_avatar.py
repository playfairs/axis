# bot.handlers.missing_avatar

from bot.base.imports import discord


def get_avatar(user: discord.User | discord.Member) -> discord.Asset:
    return user.display_avatar.with_size(128)
