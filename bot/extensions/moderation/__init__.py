from discord.ext import commands
from bot.extensions.moderation import load


async def setup(bot: commands.Bot) -> None:
    await load.setup(bot)


async def teardown(bot: commands.Bot) -> None:
    await load.teardown(bot)