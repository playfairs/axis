from datetime import datetime

from asyncpg import Pool

from bot.base.imports import DEFAULT_CONTAINER_COLOR, app_commands, commands, discord


class UsageView(discord.ui.LayoutView):
    def __init__(
        self,
        title: str,
        description: str,
        fields: list[tuple[str, str]] | None = None,
    ) -> None:
        super().__init__()
        content: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## {title}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(description),
        ]
        for name, value in fields or []:
            content.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.TextDisplay(f"### {name}\n{value}"),
                )
            )
        self.add_item(
            discord.ui.Container(*content, accent_color=DEFAULT_CONTAINER_COLOR)
        )


async def _send_usage(
    ctx: commands.Context,
    title: str,
    description: str,
    fields: list[tuple[str, str]] | None = None,
) -> None:
    await ctx.send(
        view=UsageView(title, description, fields),
        allowed_mentions=discord.AllowedMentions.none(),
    )


def _timestamp(value: datetime | None) -> str:
    if value is None:
        return "Never"
    return f"<t:{int(value.timestamp())}:R>"


def _database_pool(ctx: commands.Context) -> Pool:
    pool = getattr(ctx.bot, "database_pool", None)
    if pool is None:
        raise RuntimeError("The usage command requires the bot's database pool.")
    return pool


def _user_label(bot: commands.Bot, user_id: int) -> str:
    user = bot.get_user(user_id)
    if user is not None:
        return f"{user} (`{user_id}`)"
    return f"<@{user_id}> (`{user_id}`)"


def _guild_label(bot: commands.Bot, guild_id: int) -> str:
    guild = bot.get_guild(guild_id)
    if guild is not None:
        return f"{guild.name} (`{guild_id}`)"
    return f"`{guild_id}`"


def _parse_guild_id(value: str) -> int | None:
    normalized = value.strip().removeprefix("<#").removesuffix(">")
    try:
        guild_id = int(normalized)
    except ValueError:
        return None
    return guild_id if guild_id > 0 else None


@commands.hybrid_group(
    name="usage",
    invoke_without_command=True,
    description="Show command usage statistics.",
)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def usage_command(ctx: commands.Context) -> None:
    pool = _database_pool(ctx)
    async with pool.acquire() as connection:
        summary = await connection.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT user_id) AS users,
                   COUNT(DISTINCT guild_id) AS guilds,
                   MIN(used_at) AS first_used,
                   MAX(used_at) AS last_used
            FROM command_usage
            """
        )
        top_commands = await connection.fetch(
            """
            SELECT c.name, COUNT(*) AS uses
            FROM command_usage AS cu
            JOIN commands AS c ON c.id = cu.command_id
            GROUP BY c.id, c.name
            ORDER BY uses DESC, c.name
            LIMIT 5
            """
        )

    description = (
        f"**Total command runs:** {summary['total']:,}\n"
        f"**Tracked users:** {summary['users']:,}\n"
        f"**Tracked guilds:** {summary['guilds']:,}\n"
        f"**First run:** {_timestamp(summary['first_used'])}\n"
        f"**Last run:** {_timestamp(summary['last_used'])}"
    )
    fields: list[tuple[str, str]] = []
    if top_commands:
        fields.append(
            (
                "Top commands",
                "\n".join(
                    f"`{record['name']}` — {record['uses']:,}"
                    for record in top_commands
                ),
            )
        )
    await _send_usage(ctx, "Overall bot usage", description, fields)


@usage_command.command(name="guild", description="Show usage for a guild.")
@app_commands.describe(guild_id="Guild ID (defaults to the current guild).")
async def usage_guild(ctx: commands.Context, guild_id: str | None = None) -> None:
    target_guild_id = ctx.guild.id if guild_id is None and ctx.guild else None
    if guild_id is not None:
        target_guild_id = _parse_guild_id(guild_id)
        if target_guild_id is None:
            await _send_usage(ctx, "Guild usage", "Provide a valid guild ID.")
            return
    if target_guild_id is None:
        await _send_usage(
            ctx,
            "Guild usage",
            "Provide a guild ID when using this command outside a guild.",
        )
        return

    pool = _database_pool(ctx)
    async with pool.acquire() as connection:
        summary = await connection.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT user_id) AS users,
                   MIN(used_at) AS first_used,
                   MAX(used_at) AS last_used
            FROM command_usage
            WHERE guild_id = $1
            """,
            target_guild_id,
        )
        top_commands = await connection.fetch(
            """
            SELECT c.name, COUNT(*) AS uses
            FROM command_usage AS cu
            JOIN commands AS c ON c.id = cu.command_id
            WHERE cu.guild_id = $1
            GROUP BY c.id, c.name
            ORDER BY uses DESC, c.name
            LIMIT 5
            """,
            target_guild_id,
        )
        top_users = await connection.fetch(
            """
            SELECT user_id, COUNT(*) AS uses
            FROM command_usage
            WHERE guild_id = $1
            GROUP BY user_id
            ORDER BY uses DESC, user_id
            LIMIT 5
            """,
            target_guild_id,
        )

    description = (
        f"**Total command runs:** {summary['total']:,}\n"
        f"**Active users:** {summary['users']:,}\n"
        f"**First run:** {_timestamp(summary['first_used'])}\n"
        f"**Last run:** {_timestamp(summary['last_used'])}"
    )
    fields = []
    if top_commands:
        fields.append(
            (
                "Top commands",
                "\n".join(
                    f"`{record['name']}` — {record['uses']:,}"
                    for record in top_commands
                ),
            ),
        )
    if top_users:
        fields.append(
            (
                "Top users",
                "\n".join(
                    f"{_user_label(ctx.bot, record['user_id'])} — "
                    f"{record['uses']:,}"
                    for record in top_users
                ),
            ),
        )
    await _send_usage(
        ctx,
        f"Usage in {_guild_label(ctx.bot, target_guild_id)}",
        description,
        fields,
    )


@usage_command.command(name="user", description="Show usage for a user.")
@app_commands.describe(user="User to show (defaults to you).")
async def usage_user(
    ctx: commands.Context,
    user: discord.User | None = None,
) -> None:
    target = user or ctx.author
    pool = _database_pool(ctx)
    async with pool.acquire() as connection:
        summary = await connection.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   COUNT(DISTINCT guild_id) AS guilds,
                   MIN(used_at) AS first_used,
                   MAX(used_at) AS last_used
            FROM command_usage
            WHERE user_id = $1
            """,
            target.id,
        )
        top_commands = await connection.fetch(
            """
            SELECT c.name, COUNT(*) AS uses
            FROM command_usage AS cu
            JOIN commands AS c ON c.id = cu.command_id
            WHERE cu.user_id = $1
            GROUP BY c.id, c.name
            ORDER BY uses DESC, c.name
            LIMIT 5
            """,
            target.id,
        )
        first_command = await connection.fetchrow(
            """
            SELECT c.name, cu.used_at
            FROM command_usage AS cu
            JOIN commands AS c ON c.id = cu.command_id
            WHERE cu.user_id = $1
            ORDER BY cu.used_at, cu.id
            LIMIT 1
            """,
            target.id,
        )

    description = (
        f"**Total command runs:** {summary['total']:,}\n"
        f"**Guilds used in:** {summary['guilds']:,}\n"
        f"**First run:** {_timestamp(summary['first_used'])}\n"
        f"**Last run:** {_timestamp(summary['last_used'])}"
    )
    fields = []
    if top_commands:
        fields.append(
            (
                "Top commands",
                "\n".join(
                    f"`{record['name']}` — {record['uses']:,}"
                    for record in top_commands
                ),
            ),
        )
    if first_command is not None:
        fields.append(
            (
                "First command",
                f"`{first_command['name']}` — "
                f"{_timestamp(first_command['used_at'])}",
            ),
        )
    await _send_usage(ctx, f"Usage for {target}", description, fields)


@usage_command.command(name="command", description="Show usage for a command.")
@app_commands.describe(
    command_name="Command name, such as `serverinfo` or `role info`."
)
async def usage_command_stats(
    ctx: commands.Context,
    *,
    command_name: str,
) -> None:
    command = ctx.bot.get_command(command_name)
    if command is not None:
        command_name = command.qualified_name

    pool = _database_pool(ctx)
    async with pool.acquire() as connection:
        summary = await connection.fetchrow(
            """
            SELECT COUNT(*) AS total,
                   MIN(cu.used_at) AS first_used,
                   MAX(cu.used_at) AS last_used
            FROM command_usage AS cu
            JOIN commands AS c ON c.id = cu.command_id
            WHERE LOWER(c.name) = LOWER($1)
            """,
            command_name,
        )
        top_users = await connection.fetch(
            """
            SELECT cu.user_id, COUNT(*) AS uses
            FROM command_usage AS cu
            JOIN commands AS c ON c.id = cu.command_id
            WHERE LOWER(c.name) = LOWER($1)
            GROUP BY cu.user_id
            ORDER BY uses DESC, cu.user_id
            LIMIT 5
            """,
            command_name,
        )
        first_user = await connection.fetchrow(
            """
            SELECT cu.user_id, cu.used_at
            FROM command_usage AS cu
            JOIN commands AS c ON c.id = cu.command_id
            WHERE LOWER(c.name) = LOWER($1)
            ORDER BY cu.used_at, cu.id
            LIMIT 1
            """,
            command_name,
        )
        top_guilds = await connection.fetch(
            """
            SELECT cu.guild_id, COUNT(*) AS uses
            FROM command_usage AS cu
            JOIN commands AS c ON c.id = cu.command_id
            WHERE LOWER(c.name) = LOWER($1)
              AND cu.guild_id IS NOT NULL
            GROUP BY cu.guild_id
            ORDER BY uses DESC, cu.guild_id
            LIMIT 5
            """,
            command_name,
        )

    if summary["total"] == 0:
        await _send_usage(
            ctx,
            f"Usage for {command_name}",
            f"No usage has been recorded for `{command_name}`.",
        )
        return

    description = (
        f"**Total runs:** {summary['total']:,}\n"
        f"**First run:** {_timestamp(summary['first_used'])}\n"
        f"**Last run:** {_timestamp(summary['last_used'])}"
    )
    fields = []
    if first_user is not None:
        fields.append(
            (
                "First user",
                f"{_user_label(ctx.bot, first_user['user_id'])} — "
                f"{_timestamp(first_user['used_at'])}",
            ),
        )
    if top_users:
        fields.append(
            (
                "Top users",
                "\n".join(
                    f"{_user_label(ctx.bot, record['user_id'])} — "
                    f"{record['uses']:,}"
                    for record in top_users
                ),
            ),
        )
    if top_guilds:
        fields.append(
            (
                "Top guilds",
                "\n".join(
                    f"{_guild_label(ctx.bot, record['guild_id'])} — "
                    f"{record['uses']:,}"
                    for record in top_guilds
                ),
            ),
        )
    await _send_usage(ctx, f"Usage for {command_name}", description, fields)