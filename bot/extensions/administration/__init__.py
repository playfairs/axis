from bot.base.imports import commands
from bot.extensions.administration import load


async def setup(bot: commands.Bot) -> None:
    await load.setup(bot)


async def teardown(bot: commands.Bot) -> None:
    await load.teardown(bot)