import discord_ios

import os

import jishaku

from bot.base.imports import commands, discord, logger
from bot.config.bot import BotConfig
from bot.logging.setup import create_box
from bot.rpc.lastfm import LastFMActivity


class Axis(commands.Bot):
    def __init__(self, config: BotConfig) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned_or(*config.command_prefixes),
            intents=discord.Intents.all(),
            owner_id=config.owner_id,
            help_command=None,
        )
        self.config = config
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
                logger.info("Skipping configured extension {}", extension)
                continue

            logger.info("Loading extension {}", extension)
            await self.load_extension(extension)
            logger.info("Loaded extension {}", extension)

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

    async def _jishaku_owner_check(self, ctx: commands.Context) -> bool:
        if ctx.command is not None and ctx.command.cog_name == "Jishaku":
            return await self.is_owner(ctx.author)
        return True

    async def on_command_completion(self, ctx: commands.Context) -> None:
        timestamp = ctx.message.created_at.astimezone().strftime("%H:%M:%S")
        logger.bind(axis_box=True).info(
            create_box(
                f"✓ SUCCESS [{timestamp}]",
                [
                    f"User: {ctx.author} ({ctx.author.id})",
                    f"Guild: {ctx.guild.id if ctx.guild else 'N/A'}",
                    f"Channel: {ctx.channel.id}",
                    f"Command: {ctx.command}",
                ],
                "green",
            )
        )

    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
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

        box = create_box(title, lines, color)
        if isinstance(error, commands.CommandInvokeError):
            logger.bind(axis_box=True).opt(exception=error.original).log(
                level.upper(), box
            )
        else:
            logger.bind(axis_box=True).log(level.upper(), box)

    async def on_ready(self) -> None:
        logger.info("Connected to Discord as {}", self.user)

    async def on_error(
        self, event_method: str, *args: object, **kwargs: object
    ) -> None:
        logger.exception("Unhandled error in Discord event {}", event_method)
