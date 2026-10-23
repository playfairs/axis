from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord


class MessagesView(discord.ui.LayoutView):
    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"## {title}\n{body}"),
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )


@commands.command(
    name="messages",
    aliases=("messagecount",),
    description="Show message counts for you, a member, or the server leaderboard.",
)
@commands.guild_only()
async def messages(ctx: commands.Context, target: str | None = None) -> None:
    if ctx.guild is None:
        return
    pool = getattr(ctx.bot, "database_pool", None)
    if pool is None:
        raise RuntimeError("The messages command requires the bot's database pool.")

    if target is not None and target.casefold() == "lb":
        rows = await pool.fetch(
            """
            SELECT user_id, message_count
            FROM message_counts
            WHERE guild_id = $1
            ORDER BY message_count DESC, user_id ASC
            LIMIT 10
            """,
            ctx.guild.id,
        )
        if not rows:
            body = "No messages have been counted in this server yet."
        else:
            entries = []
            for rank, row in enumerate(rows, start=1):
                member = ctx.guild.get_member(row["user_id"])
                user_label = (
                    member.mention
                    if member is not None
                    else f"<@{row['user_id']}> (not in server)"
                )
                entries.append(
                    f"**{rank}.** {user_label} — "
                    f"**{row['message_count']:,}** messages"
                )
            body = "\n".join(entries)
        await ctx.send(
            view=MessagesView(f"message leaderboard for **{ctx.guild.name}**", body),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    member = ctx.author
    if target is not None:
        try:
            member = await commands.MemberConverter().convert(ctx, target)
        except commands.MemberNotFound:
            await ctx.send(
                view=MessagesView(
                    "Messages",
                    "I couldn't find that member in this server. Mention them "
                    "or use their ID.",
                ),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

    count = await pool.fetchval(
        """
        SELECT message_count
        FROM message_counts
        WHERE guild_id = $1 AND user_id = $2
        """,
        ctx.guild.id,
        member.id,
    )
    await ctx.send(
        view=MessagesView(
            f"messages for {member.display_name}",
            f"{member.mention} has sent **{count or 0:,}** messages in this server.",
        ),
        allowed_mentions=discord.AllowedMentions.none(),
    )