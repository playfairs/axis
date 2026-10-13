from __future__ import annotations

from bot.core.client import _metadata
from bot.base.imports import app_commands, commands, discord, logger
from bot.core.client.construct import HelpView


def _resolve_command(
    bot: commands.Bot,
    command_path: str,
) -> commands.Command | None:
    command, _ = _resolve_command_reference(bot, command_path)
    return command


def _resolve_command_reference(
    bot: commands.Bot,
    command_path: str,
) -> tuple[commands.Command | None, str | None]:
    parts = command_path.split()
    if not parts:
        return None, None

    command = bot.get_command(parts[0])
    alias_used = (
        parts[0]
        if command is not None and parts[0].casefold() != command.name.casefold()
        else None
    )
    for part in parts[1:]:
        if not isinstance(command, commands.Group):
            return None, None
        command = command.get_command(part)
        if command is None:
            return None, None
        if part.casefold() != command.name.casefold() and alias_used is None:
            alias_used = part
    return command, alias_used


@commands.hybrid_command(
    name="help",
    aliases=("h",),
    description="Browse commands or show detailed help for a command.",
)
@app_commands.describe(command_name="The command to show detailed help for.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def help_command(
    ctx: commands.Context,
    *,
    command_name: str | None = None,
) -> None:
    is_bot_owner = (
        ctx.bot.owner_ids is not None and ctx.author.id in ctx.bot.owner_ids
    )
    command = (
        _resolve_command(ctx.bot, command_name) if command_name is not None else None
    )
    if (
        command is not None
        and not is_bot_owner
        and _metadata._is_owner_command(command)
    ):
        command = None
    extension_category = (
        _metadata._extension_category(
            ctx.bot,
            command_name,
        )
        if command_name is not None and command is None
        else None
    )
    if command_name is not None and command is None and extension_category is None:
        suggestion = _metadata._command_suggestion(
            ctx.bot,
            command_name,
            include_owner_commands=is_bot_owner,
        )
        response = f"Command `{command_name}` does not exist"
        if suggestion is not None:
            response += f", perhaps you meant `{suggestion}`?"
        else:
            response += "."
        await ctx.send(response, delete_after=3)
        try:
            await ctx.message.add_reaction("❓")
        except discord.HTTPException as error:
            logger.warning(
                "Could not react to an unknown help command in channel %s (HTTP %s).",
                ctx.channel.id,
                error.status,
            )
        return
    await ctx.send(
        view=HelpView(
            ctx.bot,
            category=extension_category,
            command=command,
            command_query=command_name if extension_category is None else None,
            prefix=ctx.clean_prefix,
            is_bot_owner=is_bot_owner,
        ),
        allowed_mentions=discord.AllowedMentions.none(),
    )


@commands.command(
    name="where",
    aliases=("which",),
    description="Show which extension defines a command.",
)
async def where_command(
    ctx: commands.Context,
    *,
    command_name: str,
) -> None:
    command, alias_used = _resolve_command_reference(ctx.bot, command_name)
    if command is None:
        await ctx.send(f"No loaded command matches `{command_name}`.")
        return

    module = command.callback.__module__
    extension_prefix = "bot.extensions."
    command_name = command.qualified_name
    if alias_used is not None:
        subject = (
            f"`{alias_used}` is an alias for the `{command_name}` command, "
            "which belongs to "
        )
    else:
        subject = f"The `{command_name}` command belongs to "
    source = _metadata._source_link(module)
    if module.startswith(extension_prefix):
        extension = module[len(extension_prefix) :].partition(".")[0]
        response = f"{subject}{source}, which is part of the `{extension}` extension."
    else:
        response = f"{subject}{source}, which is part of the **Axis Core**."
    await ctx.send(response)


__all__ = ("HelpView", "help_command", "where_command")
