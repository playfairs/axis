import os
from pathlib import Path

from discord import app_commands
from dishcord import ShellSession

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
        async with ShellSession(
            cwd=str(Path(__file__).resolve().parents[5]),
            env=environment,
        ) as shell:
            output, returncode = await shell.execute("git pull")
    except (OSError, RuntimeError, TimeoutError) as error:
        await ctx.send(
            f"Couldn't run `git pull`: {error}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    if returncode != 0:
        message = f"`git pull` failed with exit code {returncode}."
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
