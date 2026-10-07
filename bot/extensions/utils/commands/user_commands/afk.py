import time

from discord import app_commands

from bot.base.bot import Axis
from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord


class AfkContainer(discord.ui.LayoutView):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(text),
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )


@commands.hybrid_command(name="afk", description="Set your AFK status.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(reason="Optional reason for being AFK.")
async def afk(
    ctx: commands.Context,
    *,
    reason: str | None = None,
) -> None:
    bot = ctx.bot
    if not isinstance(bot, Axis) or bot.database_pool is None:
        raise RuntimeError("The AFK command requires the bot's database pool.")

    reason = reason.strip() if reason and reason.strip() else None
    afk_time = int(time.time())
    await bot.database_pool.execute(
        """
        INSERT INTO afk_users (user_id, reason, afk_time)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id) DO UPDATE
        SET reason = EXCLUDED.reason, afk_time = EXCLUDED.afk_time
        """,
        ctx.author.id,
        reason,
        afk_time,
    )

    response = f"> {ctx.author.mention}: You're now AFK"
    response += f": {reason}" if reason else "."
    await ctx.send(view=AfkContainer(response))


async def on_message(message: discord.Message, *, bot: Axis) -> None:
    if message.author.bot:
        return
    if bot.database_pool is None:
        raise RuntimeError("The AFK listener requires the bot's database pool.")

    context = await bot.get_context(message)
    if not context.valid:
        afk_record = await bot.database_pool.fetchrow(
            """
            DELETE FROM afk_users
            WHERE user_id = $1
            RETURNING afk_time
            """,
            message.author.id,
        )
        if afk_record is not None:
            await message.channel.send(
                view=AfkContainer(
                    f"> {message.author.mention}: Welcome back, you went AFK: "
                    f"<t:{afk_record['afk_time']}:R>."
                ),
                delete_after=30,
            )

    mentioned_ids = list(dict.fromkeys(user.id for user in message.mentions))
    if not mentioned_ids:
        return

    afk_records = await bot.database_pool.fetch(
        """
        SELECT user_id, reason, afk_time
        FROM afk_users
        WHERE user_id = ANY($1::BIGINT[])
        """,
        mentioned_ids,
    )
    mentions_by_id = {record["user_id"]: record for record in afk_records}
    notices = []
    for user in message.mentions:
        record = mentions_by_id.get(user.id)
        if record is None:
            continue

        notice = f"> {user.mention} went AFK <t:{record['afk_time']}:R>"
        if record["reason"]:
            notice += f": **{record['reason']}**"
        notices.append(notice)

    if notices:
        await message.channel.send(
            view=AfkContainer("\n".join(notices)),
            delete_after=30,
        )
