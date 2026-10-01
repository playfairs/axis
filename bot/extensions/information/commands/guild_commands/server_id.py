from bot.base.imports import commands


@commands.command(name="serverid", aliases=("guildid", "sid"))
async def server_id(ctx: commands.Context) -> None:
    """Show the ID of the current server."""
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    await ctx.send(f"This server's ID is: `{ctx.guild.id}`")
