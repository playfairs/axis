import asyncio
from pathlib import Path
from shlex import quote

from discord import app_commands
from dishcord.discord_integration import ShellPaginatorView, ShellReader

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
    repo_path = Path(__file__).resolve().parents[5]
    command = f"env GIT_TERMINAL_PROMPT=0 git -C {quote(str(repo_path))} pull"
    reader = ShellReader(command)

    try:
        await ctx.defer(ephemeral=False)
        await reader.start()
    except (OSError, RuntimeError) as error:
        await ctx.send(
            f"Couldn't start `git pull`: {error}",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    view = ShellPaginatorView(ctx.author, reader, "git pull")
    try:
        view.message = await ctx.send(
            view.render(),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        view.start_updater()
        try:
            async for line in reader:
                if view.cancelled:
                    return
                await view.add_output(line)
        except asyncio.TimeoutError:
            if not view.cancelled:
                await view.add_output(
                    f"[timeout] No output for {reader.timeout:g} seconds"
                )
                await reader.close()

        if not view.cancelled:
            exit_status = await reader.wait()
            if exit_status == 0:
                view.transcript += "\n\nPulled the latest changes. Restarting now."
            await view.finish(exit_status)
            if exit_status == 0:
                await ctx.bot.close()
    finally:
        if not view.cancelled:
            await reader.close()
        if view._updater_task is not None and not view._updates_finished:
            view._updater_task.cancel()
