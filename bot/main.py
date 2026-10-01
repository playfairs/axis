import asyncio
import sys

from bot.base.bot import Axis
from bot.config.bot import BotConfig
from bot.config.env import EnvironmentConfig
from bot.logging.setup import configure_logging
from loguru import logger


async def start_axis() -> None:
    environment = EnvironmentConfig.load()
    bot = Axis(BotConfig())

    async with bot:
        await bot.start(environment.discord_token)


def main() -> int:
    configure_logging()
    logger.info("Starting Axis")

    try:
        asyncio.run(start_axis())
    except KeyboardInterrupt:
        logger.info("Axis shutdown requested")
    except Exception:
        logger.exception("Axis failed to start or stopped unexpectedly")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
