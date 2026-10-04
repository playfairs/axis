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
