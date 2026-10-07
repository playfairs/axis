from bot.base.imports import commands


async def on_command_completion(ctx: commands.Context) -> None:
    pool = getattr(ctx.bot, "database_pool", None)
    if pool is None:
        raise RuntimeError("The usage listener requires the bot's database pool.")

    command_name = ctx.command.qualified_name if ctx.command else ctx.invoked_with
    guild_id = ctx.guild.id if ctx.guild is not None else None

    async with pool.acquire() as connection:
        async with connection.transaction():
            command_id = await connection.fetchval(
                """
                INSERT INTO commands (name)
                VALUES ($1)
                ON CONFLICT (name) DO NOTHING
                RETURNING id
                """,
                command_name,
            )
            if command_id is None:
                command_id = await connection.fetchval(
                    "SELECT id FROM commands WHERE name = $1",
                    command_name,
                )
            await connection.execute(
                """
                INSERT INTO users (id)
                VALUES ($1)
                ON CONFLICT (id) DO NOTHING
                """,
                ctx.author.id,
            )
            if guild_id is not None:
                await connection.execute(
                    """
                    INSERT INTO guilds (id)
                    VALUES ($1)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    guild_id,
                )
            await connection.execute(
                """
                INSERT INTO command_usage (command_id, user_id, guild_id)
                VALUES ($1, $2, $3)
                """,
                command_id,
                ctx.author.id,
                guild_id,
            )