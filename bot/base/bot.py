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


import logging
import os
from typing import Any

import jishaku

from bot.base.imports import commands, discord, logger
from bot.config.bot import BotConfig
from bot.core.client.help import help_command, where_command
from bot.errors.handlers.roles import handle_role_error
from bot.logging.setup import Logger
from bot.rpc.lastfm import LastFMActivity


class Axis(commands.Bot):
    def __init__(self, config: BotConfig) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or(*config.command_prefixes),
            intents=discord.Intents.all(),
            owner_ids=config.owner_ids,
            help_command=None,
        )
        self.config = config
        self.add_command(help_command)
        self.add_command(where_command)
        self._lastfm_activity: LastFMActivity | None = None
        self.add_check(self._jishaku_owner_check)

    async def setup_hook(self) -> None:
        jishaku.Flags.HIDE = True
        jishaku.Flags.ALWAYS_DM_TRACEBACK = True
        logger.info("Loading Jishaku")
        await self.load_extension("jishaku")
        logger.info("Jishaku loaded")
        for extension in self.config.extensions:
            extension_name = extension.rsplit(".", 1)[-1]
            if extension_name in self.config.skipped_extensions:
                logger.info(f"Skipping configured extension {extension}")
                continue

            logger.info(f"Loading extension {extension}")
            await self.load_extension(extension)
            logger.info(f"Loaded extension {extension}")

        lastfm_api_key = os.getenv("LASTFM_API_KEY")
        if lastfm_api_key:
            self._lastfm_activity = LastFMActivity(self, lastfm_api_key)
            self._lastfm_activity.start()
        else:
            logger.warning(
                "LASTFM_API_KEY is not configured; Last.fm activity is disabled."
            )

    async def close(self) -> None:
        if self._lastfm_activity is not None:
            await self._lastfm_activity.close()
        await super().close()

    def dispatch(self, event: str, /, *args: Any, **kwargs: Any) -> None:
        if self.is_closed():
            return
        super().dispatch(event, *args, **kwargs)

    async def _jishaku_owner_check(self, ctx: commands.Context) -> bool:
        if ctx.command is not None and ctx.command.cog_name == "Jishaku":
            return await self.is_owner(ctx.author)
        return True

    async def on_command_completion(self, ctx: commands.Context) -> None:
        timestamp = ctx.message.created_at.astimezone().strftime("%H:%M:%S")
        box = Logger.create_box(
            f"✓ SUCCESS [{timestamp}]",
            [
                f"User: {ctx.author} ({ctx.author.id})",
                f"Guild: {ctx.guild.id if ctx.guild else 'N/A'}",
                f"Channel: {ctx.channel.id}",
                f"Command: {ctx.command}",
            ],
            "green",
        )
        logger.info(box)

    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        if await handle_role_error(ctx, error):
            return

        command = ctx.command or ctx.invoked_with
        timestamp = ctx.message.created_at.astimezone().strftime("%H:%M:%S")
        lines = [
            f"User: {ctx.author} ({ctx.author.id})",
            f"Guild: {ctx.guild.id if ctx.guild else 'N/A'}",
            f"Channel: {ctx.channel.id}",
            f"Command: {command}",
        ]

        if isinstance(error, commands.NotOwner):
            title, color, level = f"✗ OWNER_ONLY [{timestamp}]", "red", "info"
        elif isinstance(error, commands.CheckFailure):
            title, color, level = f"⚠ CHECK_FAILED [{timestamp}]", "yellow", "info"
        elif isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions)
            lines.append(f"Error: Missing permissions: {missing}")
            title, color, level = (
                f"✗ PERMISSION_ERROR [{timestamp}]",
                "red",
                "warning",
            )
        elif isinstance(error, commands.CommandNotFound):
            embed = discord.Embed(
                description=f"> {ctx.author.mention}: {ctx.invoked_with} does not exist.",
                color=discord.Colour.yellow(),
            )
            await ctx.send(embed=embed)
            title, color, level = f"? NOT_FOUND [{timestamp}]", "yellow", "info"
        elif isinstance(error, commands.CommandOnCooldown):
            lines.append(f"Error: On cooldown: {error.retry_after:.2f}s")
            title, color, level = f"⏱ COOLDOWN [{timestamp}]", "yellow", "info"
        elif isinstance(error, commands.MissingRequiredArgument):
            lines.append(f"Error: Missing argument: {error.param.name}")
            title, color, level = f"✗ MISSING_ARG [{timestamp}]", "red", "warning"
        elif isinstance(error, commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions)
            lines.append(f"Error: Missing permissions: {missing}")
            title, color, level = (
                f"✗ USER_PERM_ERROR [{timestamp}]",
                "red",
                "warning",
            )
        else:
            underlying_error = (
                error.original
                if isinstance(error, commands.CommandInvokeError)
                else error
            )
            lines.append(f"Error: {underlying_error}")
            title, color, level = f"✗ UNKNOWN_ERROR [{timestamp}]", "red", "error"

        box = Logger.create_box(title, lines, color)
        if isinstance(error, commands.CommandInvokeError):
            logger.log(
                getattr(logging, level.upper()),
                box,
                exc_info=(
                    type(error.original),
                    error.original,
                    error.original.__traceback__,
                ),
            )
        else:
            logger.log(getattr(logging, level.upper()), box)

    async def on_ready(self) -> None:
        logger.info(f"Connected to Discord as {self.user}")

    async def on_error(self, event: str, *args: object, **kwargs: object) -> None:
        logger.exception(f"Unhandled error in Discord event {event}")
