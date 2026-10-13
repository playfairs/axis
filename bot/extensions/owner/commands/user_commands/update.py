import asyncio
import os
from pathlib import Path

from discord import app_commands

from bot.base.imports import commands, discord
from bot.errors.handlers.owner_only import application_owner_check


@commands.hybrid_command(
    name="update",
    description="Pull the latest changes and restart the bot.",
)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.check(application_owner_check)
@commands.is_owner()
async def update(ctx: commands.Context) -> None:
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"

    try:
        process = await asyncio.create_subprocess_exec(
            "git",
            "pull",
            cwd=Path(__file__).resolve().parents[5],
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
    except OSError as error:
        await ctx.send(
            f"Couldn't run `git pull`: {error}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    if process.returncode != 0:
        output = (stdout + stderr).decode(errors="replace").strip()
        message = f"`git pull` failed with exit code {process.returncode}."
        if output:
            message = f"{message}\n{output[:1500]}"
        await ctx.send(
            message,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    await ctx.send(
        "Pulled the latest changes. Restarting now.",
        allowed_mentions=discord.AllowedMentions.none(),
    )
    await ctx.bot.close()
