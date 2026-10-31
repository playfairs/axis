from __future__ import annotations

import re

import asyncpg
from discord import app_commands

from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord, logger
from bot.core.client.help import help_command
from bot.extensions.utils.water import send_water_reminder

MAX_INTERVAL_SECONDS = 2**63 - 1
MAX_PING_MEMBERS = 10
INTERVAL_PATTERN = re.compile(
    r"^\s*(\d+)\s*(seconds?|minutes?|hours?|s|m|h)\s*$",
    re.IGNORECASE,
)
INTERVAL_PRESETS = {
    15 * 60: "15 minutes",
    30 * 60: "30 minutes",
    60 * 60: "1 hour",
    2 * 60 * 60: "2 hours",
    4 * 60 * 60: "4 hours",
    8 * 60 * 60: "8 hours",
    24 * 60 * 60: "24 hours",
}
UNIT_SECONDS = {
    "s": 1,
    "second": 1,
    "seconds": 1,
    "m": 60,
    "minute": 60,
    "minutes": 60,
    "h": 60 * 60,
    "hour": 60 * 60,
    "hours": 60 * 60,
}


def _database_pool(bot: object) -> asyncpg.Pool:
    pool = getattr(bot, "database_pool", None)
    if pool is None:
        raise RuntimeError("The water command requires the bot's database pool.")
    return pool


def _parse_interval(value: str) -> int | None:
    match = INTERVAL_PATTERN.fullmatch(value)
    if match is None or len(match.group(1)) > 19:
        return None

    amount = int(match.group(1))
    interval_seconds = amount * UNIT_SECONDS[match.group(2).lower()]
    if amount <= 0 or interval_seconds > MAX_INTERVAL_SECONDS:
        return None
    return interval_seconds


class _WaterChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, view: WaterConfigView) -> None:
        self.config_view = view
        defaults = []
        if view.channel_id is not None:
            channel = view.guild.get_channel(view.channel_id)
            if isinstance(channel, discord.TextChannel):
                defaults.append(channel)
        super().__init__(
            placeholder="Choose a reminder channel",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = self.values[0]
        if selected.guild_id != self.config_view.guild.id:
            await interaction.response.send_message(
                "Choose a text channel in this server.",
                ephemeral=True,
            )
            return
        channel = self.config_view.guild.get_channel(selected.id)
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Choose a text channel in this server.",
                ephemeral=True,
            )
            return
        self.config_view.channel_id = channel.id
        await self.config_view.refresh(interaction)


class _WaterIntervalSelect(discord.ui.Select):
    def __init__(self, view: WaterConfigView) -> None:
        self.config_view = view
        options = [
            discord.SelectOption(
                label=label,
                value=str(seconds),
                default=view.interval_seconds == seconds,
            )
            for seconds, label in INTERVAL_PRESETS.items()
        ]
        if view.interval_seconds not in INTERVAL_PRESETS:
            options.append(
                discord.SelectOption(
                    label=f"Custom interval: {view.interval_seconds}s",
                    value=str(view.interval_seconds),
                    default=True,
                )
            )
        super().__init__(
            placeholder="Choose a reminder interval",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.config_view.interval_seconds = int(self.values[0])
        await self.config_view.refresh(interaction)


class _WaterMemberSelect(discord.ui.UserSelect):
    def __init__(self, view: WaterConfigView) -> None:
        self.config_view = view
        defaults = [
            member
            for member_id in view.member_ids
            if (member := view.guild.get_member(member_id)) is not None
        ]
        super().__init__(
            placeholder="Choose members to ping (up to 10)",
            min_values=0,
            max_values=MAX_PING_MEMBERS,
            default_values=defaults,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.config_view.member_ids = [member.id for member in self.values]
        await self.config_view.refresh(interaction)


class _WaterConfigButton(discord.ui.Button):
    def __init__(
        self,
        view: WaterConfigView,
        *,
        label: str,
        style: discord.ButtonStyle,
        action: str,
    ) -> None:
        super().__init__(label=label, style=style)
        self.config_view = view
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        await getattr(self.config_view, self.action)(interaction)


class WaterConfigView(discord.ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        guild: discord.Guild,
        owner_id: int,
        settings: asyncpg.Record | None,
    ) -> None:
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild
        self.owner_id = owner_id
        self.enabled = settings["enabled"] if settings is not None else False
        self.originally_enabled = self.enabled
        self.channel_id = settings["channel_id"] if settings is not None else None
        self.interval_seconds = (
            settings["interval_seconds"] if settings is not None else 3600
        )
        self.member_ids = (
            list(settings["ping_member_ids"]) if settings is not None else []
        )
        self._render()

    def _render(self) -> None:
        channel_label = (
            f"<#{self.channel_id}>" if self.channel_id is not None else "Not set"
        )
        mentions = (
            ", ".join(f"<@{member_id}>" for member_id in self.member_ids)
            if self.member_ids
            else "None"
        )
        container = discord.ui.Container(
            discord.ui.TextDisplay(
                "## Water reminder configuration\n"
                f"**Enabled:** {'Yes' if self.enabled else 'No'}\n"
                f"**Channel:** {channel_label}\n"
                f"**Interval:** {self.interval_seconds} seconds\n"
                f"**Members to ping:** {mentions}\n\n"
                "Choose settings below, then select **Apply** to save them. "
                "Enable and Disable take effect immediately."
            ),
            discord.ui.Separator(),
            discord.ui.ActionRow(_WaterChannelSelect(self)),
            discord.ui.ActionRow(_WaterIntervalSelect(self)),
            discord.ui.ActionRow(_WaterMemberSelect(self)),
            discord.ui.ActionRow(
                _WaterConfigButton(
                    self,
                    label="Disable" if self.enabled else "Enable",
                    style=(
                        discord.ButtonStyle.secondary
                        if self.enabled
                        else discord.ButtonStyle.success
                    ),
                    action="disable_now" if self.enabled else "enable_now",
                ),
                _WaterConfigButton(
                    self,
                    label="Clear channel",
                    style=discord.ButtonStyle.secondary,
                    action="clear_channel",
                ),
                _WaterConfigButton(
                    self,
                    label="Apply",
                    style=discord.ButtonStyle.primary,
                    action="apply",
                ),
                _WaterConfigButton(
                    self,
                    label="Cancel",
                    style=discord.ButtonStyle.danger,
                    action="cancel",
                ),
            ),
            accent_color=DEFAULT_CONTAINER_COLOR,
        )
        self.clear_items()
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        if (
            interaction.guild_id != self.guild.id
            or member.id != self.owner_id
            or not isinstance(member, discord.Member)
            or not member.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                "Only the server manager who opened this panel can use it.",
                ephemeral=True,
            )
            return False
        return True

    async def refresh(self, interaction: discord.Interaction) -> None:
        self._render()
        await interaction.response.edit_message(view=self)

    async def _set_enabled(
        self,
        interaction: discord.Interaction,
        enabled: bool,
    ) -> None:
        if enabled and self.channel_id is None:
            await interaction.response.send_message(
                "Choose a reminder channel before enabling water reminders.",
                ephemeral=True,
            )
            return

        channel = (
            self.guild.get_channel(self.channel_id)
            if self.channel_id is not None
            else None
        )
        if self.channel_id is not None and not isinstance(
            channel, discord.TextChannel
        ):
            await interaction.response.send_message(
                "The selected reminder channel is no longer available.",
                ephemeral=True,
            )
            return
        if enabled and isinstance(channel, discord.TextChannel):
            bot_member = self.guild.me
            permissions = (
                channel.permissions_for(bot_member)
                if bot_member is not None
                else discord.Permissions.none()
            )
            if not permissions.view_channel or not permissions.send_messages:
                await interaction.response.send_message(
                    "I need permission to view and send messages in the selected "
                    "channel.",
                    ephemeral=True,
                )
                return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            pool = _database_pool(self.bot)
            await pool.execute(
                """
                INSERT INTO water_settings (
                    guild_id, enabled, channel_id, interval_seconds,
                    ping_member_ids, next_reminder_at
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    CASE WHEN $2
                        THEN NOW() + ($4::BIGINT * INTERVAL '1 second')
                        ELSE NULL
                    END
                )
                ON CONFLICT (guild_id)
                DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    channel_id = EXCLUDED.channel_id,
                    interval_seconds = EXCLUDED.interval_seconds,
                    ping_member_ids = EXCLUDED.ping_member_ids,
                    next_reminder_at = CASE
                        WHEN EXCLUDED.enabled THEN
                            NOW() + (
                                EXCLUDED.interval_seconds
                                * INTERVAL '1 second'
                            )
                        ELSE NULL
                    END
                """,
                self.guild.id,
                enabled,
                self.channel_id,
                self.interval_seconds,
                self.member_ids,
            )
        except asyncpg.PostgresError:
            logger.exception(
                "Could not change water reminder state for guild %s.",
                self.guild.id,
            )
            await interaction.followup.send(
                "Could not update water reminders. Please try again.",
                ephemeral=True,
            )
            return

        self.enabled = enabled
        self.originally_enabled = enabled
        self._render()
        await interaction.message.edit(view=self)
        if enabled:
            sent = await send_water_reminder(
                self.bot,
                pool,
                guild_id=self.guild.id,
                channel_id=self.channel_id,
                interval_seconds=self.interval_seconds,
                ping_member_ids=self.member_ids,
            )
            response = (
                "Water reminders are now enabled, and the first reminder was "
                "sent."
                if sent
                else "Water reminders are now enabled, but I couldn't send the "
                "first reminder. I'll retry automatically."
            )
        else:
            response = "Water reminders are now disabled."
        await interaction.followup.send(response, ephemeral=True)

    async def enable_now(self, interaction: discord.Interaction) -> None:
        await self._set_enabled(interaction, True)

    async def disable_now(self, interaction: discord.Interaction) -> None:
        await self._set_enabled(interaction, False)

    async def clear_channel(self, interaction: discord.Interaction) -> None:
        self.channel_id = None
        await self.refresh(interaction)

    async def apply(self, interaction: discord.Interaction) -> None:
        if self.enabled and self.channel_id is None:
            await interaction.response.send_message(
                "Choose a reminder channel before enabling water reminders.",
                ephemeral=True,
            )
            return
        channel = (
            self.guild.get_channel(self.channel_id)
            if self.channel_id is not None
            else None
        )
        if self.channel_id is not None and not isinstance(
            channel, discord.TextChannel
        ):
            await interaction.response.send_message(
                "The selected reminder channel is no longer available.",
                ephemeral=True,
            )
            return
        if isinstance(channel, discord.TextChannel):
            bot_member = self.guild.me
            permissions = (
                channel.permissions_for(bot_member)
                if bot_member is not None
                else discord.Permissions.none()
            )
            if not permissions.view_channel or not permissions.send_messages:
                await interaction.response.send_message(
                    "I need permission to view and send messages in the selected "
                    "channel.",
                    ephemeral=True,
                )
                return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            pool = _database_pool(self.bot)
            await pool.execute(
                """
                INSERT INTO water_settings (
                    guild_id, enabled, channel_id, interval_seconds,
                    ping_member_ids, next_reminder_at
                )
                VALUES (
                    $1, $2, $3, $4, $5,
                    CASE WHEN $2
                        THEN NOW() + ($4::BIGINT * INTERVAL '1 second')
                        ELSE NULL
                    END
                )
                ON CONFLICT (guild_id)
                DO UPDATE SET
                    enabled = EXCLUDED.enabled,
                    channel_id = EXCLUDED.channel_id,
                    interval_seconds = EXCLUDED.interval_seconds,
                    ping_member_ids = EXCLUDED.ping_member_ids,
                    next_reminder_at = CASE
                        WHEN EXCLUDED.enabled
                            AND NOT water_settings.enabled THEN
                                NOW() + (
                                    EXCLUDED.interval_seconds
                                    * INTERVAL '1 second'
                                )
                        WHEN EXCLUDED.enabled
                            THEN COALESCE(
                                water_settings.next_reminder_at,
                                NOW() + (
                                    EXCLUDED.interval_seconds
                                    * INTERVAL '1 second'
                                )
                            )
                        ELSE NULL
                    END
                """,
                self.guild.id,
                self.enabled,
                self.channel_id,
                self.interval_seconds,
                self.member_ids,
            )
        except asyncpg.PostgresError:
            logger.exception(
                "Could not apply water reminder config for guild %s.",
                self.guild.id,
            )
            await interaction.followup.send(
                "Could not save the water reminder configuration. Please try "
                "again later.",
                ephemeral=True,
            )
            return

        self._render()
        await interaction.message.edit(view=self)
        if self.enabled and not self.originally_enabled:
            sent = await send_water_reminder(
                self.bot,
                pool,
                guild_id=self.guild.id,
                channel_id=self.channel_id,
                interval_seconds=self.interval_seconds,
                ping_member_ids=self.member_ids,
            )
            self.originally_enabled = True
            result = (
                "Water reminder configuration applied and the first reminder "
                "was sent."
                if sent
                else "Water reminders are enabled, but I couldn't send the "
                "first reminder. I'll retry automatically."
            )
        else:
            result = "Water reminder configuration applied."
        await interaction.followup.send(result, ephemeral=True)

    async def cancel(self, interaction: discord.Interaction) -> None:
        self.stop()
        await interaction.response.edit_message(view=None)


@commands.hybrid_group(
    name="water",
    invoke_without_command=True,
    description="Configure water reminders for this server.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def water(ctx: commands.Context) -> None:
    await ctx.invoke(help_command, command_name="water")


@water.command(name="enable", description="Enable water reminders.")
async def water_enable(ctx: commands.Context) -> None:
    if ctx.guild is None:
        raise RuntimeError("The water command must be used in a server.")
    pool = _database_pool(ctx.bot)
    settings = await pool.fetchrow(
        """
        SELECT channel_id, interval_seconds, ping_member_ids
        FROM water_settings
        WHERE guild_id = $1
        """,
        ctx.guild.id,
    )
    if settings is None or settings["channel_id"] is None:
        await ctx.send(
            "Set a reminder channel with `water channel` before enabling "
            "water reminders.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    await pool.execute(
        """
        INSERT INTO water_settings (guild_id, enabled, next_reminder_at)
        VALUES (
            $1, TRUE,
            NOW() + (3600 * INTERVAL '1 second')
        )
        ON CONFLICT (guild_id)
        DO UPDATE SET
            enabled = TRUE,
            next_reminder_at = NOW()
                + (water_settings.interval_seconds * INTERVAL '1 second')
        """,
        ctx.guild.id,
    )
    sent = await send_water_reminder(
        ctx.bot,
        pool,
        guild_id=ctx.guild.id,
        channel_id=settings["channel_id"],
        interval_seconds=settings["interval_seconds"],
        ping_member_ids=settings["ping_member_ids"],
    )
    response = (
        "Water reminders are enabled and the first reminder was sent."
        if sent
        else "Water reminders are enabled, but I couldn't send the first "
        "reminder. I'll retry automatically."
    )
    await ctx.send(response, allowed_mentions=discord.AllowedMentions.none())


@water.command(name="disable", description="Disable water reminders.")
async def water_disable(ctx: commands.Context) -> None:
    if ctx.guild is None:
        raise RuntimeError("The water command must be used in a server.")
    await _database_pool(ctx.bot).execute(
        """
        INSERT INTO water_settings (guild_id, enabled)
        VALUES ($1, FALSE)
        ON CONFLICT (guild_id)
        DO UPDATE SET enabled = FALSE, next_reminder_at = NULL
        """,
        ctx.guild.id,
    )
    await ctx.send(
        "Water reminders are disabled.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@water.command(
    name="reset",
    description="Reset all water reminder settings for this server.",
)
async def water_reset(ctx: commands.Context) -> None:
    if ctx.guild is None:
        raise RuntimeError("The water command must be used in a server.")
    await _database_pool(ctx.bot).execute(
        "DELETE FROM water_settings WHERE guild_id = $1",
        ctx.guild.id,
    )
    await ctx.send(
        "Water reminder settings have been reset. Reminders are disabled, "
        "with no channel or ping members configured.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@water.command(
    name="channel",
    description="Set the water reminder channel (defaults to this channel).",
)
@app_commands.describe(channel="The text channel for water reminders.")
async def water_channel(
    ctx: commands.Context,
    channel: discord.TextChannel | None = None,
) -> None:
    if ctx.guild is None:
        raise RuntimeError("The water command must be used in a server.")
    target = channel or ctx.channel
    if not isinstance(target, discord.TextChannel) or target.guild.id != ctx.guild.id:
        await ctx.send(
            "Choose a text channel in this server.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    await _database_pool(ctx.bot).execute(
        """
        INSERT INTO water_settings (guild_id, channel_id)
        VALUES ($1, $2)
        ON CONFLICT (guild_id)
        DO UPDATE SET channel_id = EXCLUDED.channel_id
        """,
        ctx.guild.id,
        target.id,
    )
    await ctx.send(
        f"Water reminders will be sent to {target.mention}.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@water.command(
    name="int",
    aliases=["interval", "threshold"],
    description="Set how often water reminders are sent.",
)
@app_commands.describe(value="A duration such as 30m, 1hour, or 3600s.")
async def water_interval(ctx: commands.Context, value: str) -> None:
    if ctx.guild is None:
        raise RuntimeError("The water command must be used in a server.")
    interval_seconds = _parse_interval(value)
    if interval_seconds is None:
        await ctx.send(
            "Use a positive interval such as `30m`, `1hour`, or `3600s`.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    await _database_pool(ctx.bot).execute(
        """
        INSERT INTO water_settings (
            guild_id, interval_seconds, next_reminder_at
        )
        VALUES (
            $1, $2, NOW() + ($2::BIGINT * INTERVAL '1 second')
        )
        ON CONFLICT (guild_id)
        DO UPDATE SET
            interval_seconds = EXCLUDED.interval_seconds,
            next_reminder_at = CASE
                WHEN water_settings.enabled THEN
                    NOW() + (EXCLUDED.interval_seconds * INTERVAL '1 second')
                ELSE NULL
            END
        """,
        ctx.guild.id,
        interval_seconds,
    )
    await ctx.send(
        f"Water reminder interval set to {interval_seconds} seconds.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@water.command(
    name="config",
    description="Edit and apply this server's water reminder config.",
)
async def water_config(ctx: commands.Context) -> None:
    if ctx.guild is None:
        raise RuntimeError("The water command must be used in a server.")

    settings = await _database_pool(ctx.bot).fetchrow(
        """
        SELECT enabled, channel_id, interval_seconds, ping_member_ids
        FROM water_settings
        WHERE guild_id = $1
        """,
        ctx.guild.id,
    )
    view = WaterConfigView(
        ctx.bot,
        ctx.guild,
        ctx.author.id,
        settings,
    )
    if ctx.interaction is not None:
        await ctx.interaction.response.send_message(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True,
        )
    else:
        await ctx.send(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )


@water.group(
    name="ping",
    invoke_without_command=True,
    description="Configure members to ping with water reminders.",
)
async def water_ping(ctx: commands.Context) -> None:
    if ctx.guild is None:
        raise RuntimeError("The water command must be used in a server.")
    settings = await _database_pool(ctx.bot).fetchrow(
        "SELECT ping_member_ids FROM water_settings WHERE guild_id = $1",
        ctx.guild.id,
    )
    member_ids = settings["ping_member_ids"] if settings is not None else []
    pings = ", ".join(f"<@{member_id}>" for member_id in member_ids) or "None"
    await ctx.send(
        f"Water reminder pings: {pings}. Use `water ping add <member>`, "
        "`water ping remove <member>`, or `water ping clear`.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@water_ping.command(name="add", description="Add a member to water reminder pings.")
async def water_ping_add(
    ctx: commands.Context,
    member: discord.Member,
) -> None:
    if ctx.guild is None:
        raise RuntimeError("The water command must be used in a server.")
    await _database_pool(ctx.bot).execute(
        """
        INSERT INTO water_settings (guild_id, ping_member_ids)
        VALUES ($1, ARRAY[$2]::BIGINT[])
        ON CONFLICT (guild_id)
        DO UPDATE SET ping_member_ids = CASE
            WHEN $2 = ANY(water_settings.ping_member_ids)
                THEN water_settings.ping_member_ids
            ELSE array_append(water_settings.ping_member_ids, $2)
        END
        """,
        ctx.guild.id,
        member.id,
    )
    await ctx.send(
        f"{member.mention} will be pinged with water reminders.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@water_ping.command(
    name="remove",
    description="Remove a member from water reminder pings.",
)
async def water_ping_remove(
    ctx: commands.Context,
    member: discord.Member,
) -> None:
    if ctx.guild is None:
        raise RuntimeError("The water command must be used in a server.")
    await _database_pool(ctx.bot).execute(
        """
        INSERT INTO water_settings (guild_id, ping_member_ids)
        VALUES ($1, '{}'::BIGINT[])
        ON CONFLICT (guild_id)
        DO UPDATE SET
            ping_member_ids = array_remove(
                water_settings.ping_member_ids, $2
            )
        """,
        ctx.guild.id,
        member.id,
    )
    await ctx.send(
        f"{member.mention} will no longer be pinged with water reminders.",
        allowed_mentions=discord.AllowedMentions.none(),
    )


@water_ping.command(name="clear", description="Clear all water reminder pings.")
async def water_ping_clear(ctx: commands.Context) -> None:
    if ctx.guild is None:
        raise RuntimeError("The water command must be used in a server.")
    await _database_pool(ctx.bot).execute(
        """
        INSERT INTO water_settings (guild_id, ping_member_ids)
        VALUES ($1, '{}'::BIGINT[])
        ON CONFLICT (guild_id)
        DO UPDATE SET ping_member_ids = '{}'::BIGINT[]
        """,
        ctx.guild.id,
    )
    await ctx.send(
        "Water reminder pings cleared.",
        allowed_mentions=discord.AllowedMentions.none(),
    )
