from __future__ import annotations

import asyncpg

from discord import app_commands

from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord, logger
from bot.converters import (
    MessageTemplate,
    MessageTemplateConverter,
    MessageTemplateError,
)

TEMPLATE_CONVERTER = MessageTemplateConverter()
MESSAGE_LIMIT = 2000


def _database_pool(bot: object) -> asyncpg.Pool:
    pool = getattr(bot, "database_pool", None)
    if pool is None:
        raise RuntimeError("The gate commands require the bot's database pool.")
    return pool


async def _load_settings(
    bot: object,
    guild_id: int,
) -> asyncpg.Record | None:
    return await _database_pool(bot).fetchrow(
        """
        SELECT enabled, channel_id, welcome_message, goodbye_message, dm_message
        FROM gate_settings
        WHERE guild_id = $1
        """,
        guild_id,
    )


async def _set_setting(
    bot: object,
    guild_id: int,
    column: str,
    value: object,
) -> None:
    if column not in {
        "enabled",
        "channel_id",
        "welcome_message",
        "goodbye_message",
        "dm_message",
    }:
        raise ValueError(f"Unknown gate setting: {column}")
    if column == "enabled":
        await _database_pool(bot).execute(
            """
            INSERT INTO gate_settings (guild_id, enabled)
            VALUES ($1, $2)
            ON CONFLICT (guild_id)
            DO UPDATE SET enabled = EXCLUDED.enabled, updated_at = NOW()
            """,
            guild_id,
            value,
        )
        return
    await _database_pool(bot).execute(
        f"""
        INSERT INTO gate_settings (guild_id, enabled, {column})
        VALUES ($1, FALSE, $2)
        ON CONFLICT (guild_id)
        DO UPDATE SET {column} = EXCLUDED.{column}, updated_at = NOW()
        """,
        guild_id,
        value,
    )


async def _enable_if_ready(bot: object, guild_id: int) -> bool:
    settings = await _load_settings(bot, guild_id)
    if settings is None:
        return False
    has_channel_message = bool(
        settings["welcome_message"] or settings["goodbye_message"]
    )
    has_message = bool(has_channel_message or settings["dm_message"])
    if (
        has_message
        and (not has_channel_message or settings["channel_id"] is not None)
        and not settings["enabled"]
    ):
        await _set_setting(bot, guild_id, "enabled", True)
        return True
    return bool(settings["enabled"])


def _template_context(
    bot: commands.Bot,
    member: discord.Member,
    channel: discord.TextChannel | None,
) -> dict[str, object]:
    return {
        "user": member,
        "member": member,
        "guild": member.guild,
        "server": member.guild,
        "channel": channel,
        "bot": bot,
    }


def _render_message(
    template: str,
    bot: commands.Bot,
    member: discord.Member,
    channel: discord.TextChannel | None,
) -> str:
    return MessageTemplate(template, ()).render(
        **_template_context(bot, member, channel)
    )


def _allowed_mentions(member: discord.Member) -> discord.AllowedMentions:
    return discord.AllowedMentions(
        everyone=False,
        users=[member],
        roles=False,
        replied_user=False,
    )


async def _send_channel_template(
    bot: commands.Bot,
    member: discord.Member,
    settings: asyncpg.Record,
    column: str,
) -> None:
    template = settings[column]
    if not template:
        return
    channel_id = settings["channel_id"]
    channel = (
        member.guild.get_channel(channel_id)
        if channel_id is not None
        else None
    )
    if not isinstance(channel, discord.TextChannel):
        logger.warning(
            "Gate %s channel is missing in guild %s.",
            column,
            member.guild.id,
        )
        return
    try:
        await channel.send(
            _render_message(template, bot, member, channel),
            allowed_mentions=_allowed_mentions(member),
        )
    except MessageTemplateError as error:
        logger.warning(
            "Invalid gate %s template in guild %s: %s",
            column,
            member.guild.id,
            error,
        )
    except discord.HTTPException:
        logger.exception(
            "Could not send gate %s message for member %s in guild %s.",
            column,
            member.id,
            member.guild.id,
        )


async def on_member_join(bot: commands.Bot, member: discord.Member) -> None:
    settings = await _load_settings(bot, member.guild.id)
    if settings is None or not settings["enabled"]:
        return
    await _send_channel_template(bot, member, settings, "welcome_message")

    template = settings["dm_message"]
    if not template:
        return
    channel_id = settings["channel_id"]
    channel = (
        member.guild.get_channel(channel_id)
        if channel_id is not None
        else None
    )
    try:
        await member.send(
            _render_message(template, bot, member, channel),
            allowed_mentions=_allowed_mentions(member),
        )
    except MessageTemplateError as error:
        logger.warning(
            "Invalid gate DM template in guild %s: %s",
            member.guild.id,
            error,
        )
    except discord.HTTPException:
        logger.exception(
            "Could not send gate DM to member %s in guild %s.",
            member.id,
            member.guild.id,
        )


async def on_member_remove(bot: commands.Bot, member: discord.Member) -> None:
    settings = await _load_settings(bot, member.guild.id)
    if settings is None or not settings["enabled"]:
        return
    await _send_channel_template(bot, member, settings, "goodbye_message")


listeners = {
    "on_member_join": on_member_join,
    "on_member_remove": on_member_remove,
}


def _template_summary(template: str | None) -> str:
    if not template:
        return "Not set"
    return template[:1021] + ("…" if len(template) > 1024 else "")


def _settings_embed(
    guild: discord.Guild,
    settings: asyncpg.Record | None,
) -> discord.Embed:
    embed = discord.Embed(title=f"Gate settings — {guild.name}")
    if settings is None:
        embed.description = "Gate is not configured.\nStatus: **Disabled**"
        return embed
    channel_id = settings["channel_id"]
    channel = guild.get_channel(channel_id) if channel_id is not None else None
    embed.add_field(
        name="Status",
        value="Enabled" if settings["enabled"] else "Disabled",
        inline=True,
    )
    embed.add_field(
        name="Channel",
        value=channel.mention if channel is not None else "Not set",
        inline=True,
    )
    embed.add_field(
        name="Welcome message",
        value=_template_summary(settings["welcome_message"]),
        inline=False,
    )
    embed.add_field(
        name="Goodbye message",
        value=_template_summary(settings["goodbye_message"]),
        inline=False,
    )
    embed.add_field(
        name="Join DM",
        value=_template_summary(settings["dm_message"]),
        inline=False,
    )
    if not settings["enabled"]:
        embed.description = (
            "Settings are saved but gate messages are currently **disabled**. "
            "Use `gate enable` to enable them."
        )
    return embed


async def _show_setting(
    ctx: commands.Context,
    column: str,
) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    settings = await _load_settings(ctx.bot, ctx.guild.id)
    value = settings[column] if settings is not None else None
    await ctx.send(
        f"`{value or 'Not set'}`",
        allowed_mentions=discord.AllowedMentions.none(),
    )


class GateChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, view: GateConfigView) -> None:
        self.config_view = view
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Choose the gate message channel",
            min_values=0,
            max_values=1,
            required=False,
            default_values=[view.channel] if view.channel is not None else [],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        selected = self.values[0] if self.values else None
        channel = (
            guild.get_channel(selected.id)
            if guild is not None and selected is not None
            else None
        )
        if selected is not None and not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "Choose a text channel in this server.",
                ephemeral=True,
            )
            return
        self.config_view.channel = channel
        self.default_values = [channel] if channel is not None else []
        await self.config_view.refresh(interaction)


class GateMessageModal(discord.ui.Modal):
    def __init__(
        self,
        view: GateConfigView,
        field: str,
        title: str,
        current_value: str | None,
    ) -> None:
        super().__init__(title=title, timeout=300)
        self.config_view = view
        self.field = field
        self.template_input = discord.ui.TextInput(
            label="Message template (leave blank to clear)",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=MESSAGE_LIMIT,
            default=current_value or "",
            placeholder="Example: Hi, {user.mention}! Welcome to {guild.name}.",
        )
        self.add_item(self.template_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if (
            interaction.user.id != self.config_view.owner_id
            or interaction.guild_id != self.config_view.guild.id
        ):
            await interaction.response.send_message(
                "This configuration belongs to a different user or server.",
                ephemeral=True,
            )
            return
        value = self.template_input.value.strip() or None
        if value is not None:
            try:
                await TEMPLATE_CONVERTER.convert(self.config_view.ctx, value)
            except MessageTemplateError as error:
                await interaction.response.send_message(str(error), ephemeral=True)
                return
        self.config_view.messages[self.field] = value
        await self.config_view.refresh_message()
        await interaction.response.send_message(
            f"{self.config_view.message_label(self.field)} "
            f"{'cleared' if value is None else 'staged'}. "
            "Click Apply in the configuration panel to save.",
            ephemeral=True,
        )


class GateMessageSelect(discord.ui.Select):
    def __init__(self, view: GateConfigView) -> None:
        self.config_view = view
        super().__init__(
            placeholder="Choose a message to set up",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Welcome message",
                    value="welcome_message",
                    description="Sent to the selected channel when someone joins.",
                ),
                discord.SelectOption(
                    label="Goodbye message",
                    value="goodbye_message",
                    description="Sent to the selected channel when someone leaves.",
                ),
                discord.SelectOption(
                    label="Join DM",
                    value="dm_message",
                    description="Sent directly to each new member.",
                ),
            ],
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        field = self.values[0]
        await interaction.response.send_modal(
            GateMessageModal(
                self.config_view,
                field,
                f"Set {self.config_view.message_label(field)}",
                self.config_view.messages[field],
            )
        )


class GateConfigView(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        settings: asyncpg.Record | None,
    ) -> None:
        super().__init__(timeout=300)
        if ctx.guild is None:
            raise RuntimeError("Gate configuration requires a server.")
        self.ctx = ctx
        self.bot = ctx.bot
        self.guild = ctx.guild
        self.owner_id = ctx.author.id
        self.interaction = ctx.interaction
        channel_id = settings["channel_id"] if settings is not None else None
        selected_channel = (
            self.guild.get_channel(channel_id)
            if channel_id is not None
            else None
        )
        self.channel = (
            selected_channel
            if isinstance(selected_channel, discord.TextChannel)
            else None
        )
        self.messages: dict[str, str | None] = {
            "welcome_message": (
                settings["welcome_message"] if settings is not None else None
            ),
            "goodbye_message": (
                settings["goodbye_message"] if settings is not None else None
            ),
            "dm_message": settings["dm_message"] if settings is not None else None,
        }
        self.message: discord.Message | None = None
        self.add_item(GateChannelSelect(self))
        self.add_item(GateMessageSelect(self))

    @staticmethod
    def message_label(field: str) -> str:
        return {
            "welcome_message": "Welcome message",
            "goodbye_message": "Goodbye message",
            "dm_message": "Join DM",
        }[field]

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="Gate message setup",
            description=(
                f"**{self.guild.name}**\n"
                "Choose a channel, select a message to edit, then Apply your "
                "changes."
            ),
            color=DEFAULT_CONTAINER_COLOR,
        )
        embed.add_field(
            name="Message channel",
            value=self.channel.mention if self.channel is not None else "Not set",
            inline=True,
        )
        for field in ("welcome_message", "goodbye_message", "dm_message"):
            template = self.messages[field]
            label = self.message_label(field)
            status = "Configured" if template else "Not configured"
            embed.add_field(
                name=f"{label} - {status}",
                value=(
                    discord.utils.escape_markdown(_template_summary(template))
                    if template
                    else "Set this message from the dropdown above."
                ),
                inline=False,
            )
        embed.set_footer(
            text=(
                "Changes are staged until you click Apply. "
                "Leave a message blank to clear it."
            )
        )
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the person who opened this configuration can use it.",
                ephemeral=True,
            )
            return False
        if interaction.guild_id != self.guild.id:
            await interaction.response.send_message(
                "This configuration belongs to a different server.",
                ephemeral=True,
            )
            return False
        return True

    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self,
        )

    async def refresh_message(self) -> None:
        if self.interaction is not None:
            self.message = await self.interaction.edit_original_response(
                embed=self.build_embed(),
                view=self,
            )
        elif self.message is not None:
            self.message = await self.message.edit(
                embed=self.build_embed(),
                view=self,
            )

    @discord.ui.button(label="Apply changes", style=discord.ButtonStyle.success, row=2)
    async def apply(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel_message_is_set = any(
            (
                self.messages["welcome_message"],
                self.messages["goodbye_message"],
            )
        )
        if self.channel is None and channel_message_is_set:
            await interaction.followup.send(
                "Choose a channel before applying welcome or goodbye messages.",
                ephemeral=True,
            )
            return
        if self.channel is not None:
            bot_member = self.guild.me
            permissions = (
                self.channel.permissions_for(bot_member)
                if bot_member is not None
                else discord.Permissions.none()
            )
            if not permissions.view_channel or not permissions.send_messages:
                await interaction.followup.send(
                    "I need permission to view and send messages in the selected "
                    "channel.",
                    ephemeral=True,
                )
                return

        for template in self.messages.values():
            if template:
                try:
                    await TEMPLATE_CONVERTER.convert(self.ctx, template)
                except MessageTemplateError as error:
                    await interaction.followup.send(str(error), ephemeral=True)
                    return

        try:
            await _database_pool(self.bot).execute(
                """
                INSERT INTO gate_settings (
                    guild_id, enabled, channel_id, welcome_message,
                    goodbye_message, dm_message
                )
                VALUES ($1, FALSE, $2, $3, $4, $5)
                ON CONFLICT (guild_id)
                DO UPDATE SET
                    channel_id = EXCLUDED.channel_id,
                    welcome_message = EXCLUDED.welcome_message,
                    goodbye_message = EXCLUDED.goodbye_message,
                    dm_message = EXCLUDED.dm_message,
                    updated_at = NOW()
                """,
                self.guild.id,
                self.channel.id if self.channel is not None else None,
                self.messages["welcome_message"],
                self.messages["goodbye_message"],
                self.messages["dm_message"],
            )
        except asyncpg.PostgresError:
            logger.exception(
                "Could not save gate configuration for guild %s.",
                self.guild.id,
            )
            await interaction.followup.send(
                "I couldn't save these settings. Please try again.",
                ephemeral=True,
            )
            return

        await _enable_if_ready(self.bot, self.guild.id)
        self.stop()
        if self.interaction is not None:
            self.message = await self.interaction.edit_original_response(
                embed=self.build_embed(),
                view=None,
            )
        elif self.message is not None:
            self.message = await self.message.edit(
                embed=self.build_embed(),
                view=None,
            )
        await interaction.followup.send(
            "Gate settings applied.",
            ephemeral=True,
        )

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, row=2)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        self.stop()
        await interaction.response.edit_message(
            content="Gate configuration cancelled.",
            embed=None,
            view=None,
        )

    async def on_timeout(self) -> None:
        if self.message is not None:
            await self.message.edit(
                content="Gate configuration expired.",
                embed=None,
                view=None,
            )


@commands.hybrid_group(
    name="gate",
    invoke_without_command=True,
    description="Configure server join and leave messages.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def gate(ctx: commands.Context) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    settings = await _load_settings(ctx.bot, ctx.guild.id)
    await ctx.send(
        embed=_settings_embed(ctx.guild, settings),
        allowed_mentions=discord.AllowedMentions.none(),
    )


@gate.command(name="channel", description="Set the join/leave message channel.")
@app_commands.describe(channel="The text channel for welcome and goodbye messages.")
async def gate_channel(
    ctx: commands.Context,
    channel: discord.TextChannel | None = None,
) -> None:
    if channel is None:
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.")
            return
        settings = await _load_settings(ctx.bot, ctx.guild.id)
        channel_id = settings["channel_id"] if settings is not None else None
        current = (
            ctx.guild.get_channel(channel_id)
            if channel_id is not None
            else None
        )
        await ctx.send(
            f"Current gate channel: {current.mention if current else 'Not set'}.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return
    if ctx.guild is None or channel.guild != ctx.guild:
        await ctx.send("Choose a text channel from this server.")
        return
    bot_member = ctx.guild.me
    if bot_member is None:
        await ctx.send("I couldn't verify my permissions in this server.")
        return
    permissions = channel.permissions_for(bot_member)
    if not permissions.view_channel or not permissions.send_messages:
        await ctx.send(
            "I need permission to view and send messages in that channel."
        )
        return
    await _set_setting(ctx.bot, ctx.guild.id, "channel_id", channel.id)
    enabled = await _enable_if_ready(ctx.bot, ctx.guild.id)
    await ctx.send(
        f"Gate messages will use {channel.mention}."
        + (" Gate messages are now enabled." if enabled else ""),
        allowed_mentions=discord.AllowedMentions.none(),
    )


@gate.command(name="welcome", description="Set the message sent when someone joins.")
@app_commands.describe(
    action="Use set.",
    message="Message template, for example: Hi, {user.mention}!",
)
async def gate_welcome(
    ctx: commands.Context,
    action: str | None = None,
    *,
    message: str | None = None,
) -> None:
    if action is None:
        await _show_setting(ctx, "welcome_message")
        return
    if action.casefold() != "set":
        await ctx.send("Use `gate welcome set <message>`.")
        return
    if message is None:
        await ctx.send("Provide a welcome message template.")
        return
    await _set_template(ctx, "welcome_message", message)


@gate.command(name="goodbye", description="Set the message sent when someone leaves.")
@app_commands.describe(
    action="Use set.",
    message="Message template, for example: {user.name} left {guild.name}.",
)
async def gate_goodbye(
    ctx: commands.Context,
    action: str | None = None,
    *,
    message: str | None = None,
) -> None:
    if action is None:
        await _show_setting(ctx, "goodbye_message")
        return
    if action.casefold() != "set":
        await ctx.send("Use `gate goodbye set <message>`.")
        return
    if message is None:
        await ctx.send("Provide a goodbye message template.")
        return
    await _set_template(ctx, "goodbye_message", message)


async def _set_template(
    ctx: commands.Context,
    column: str,
    value: str,
) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    value = value.strip()
    if not value:
        await ctx.send("The message cannot be empty.")
        return
    if len(value) > MESSAGE_LIMIT:
        await ctx.send(f"Messages must be {MESSAGE_LIMIT} characters or fewer.")
        return
    try:
        await TEMPLATE_CONVERTER.convert(ctx, value)
    except MessageTemplateError as error:
        await ctx.send(str(error))
        return
    await _set_setting(ctx.bot, ctx.guild.id, column, value)
    enabled = await _enable_if_ready(ctx.bot, ctx.guild.id)
    await ctx.send(
        f"Updated the {column.replace('_', ' ')} template."
        + (" Gate messages are now enabled." if enabled else ""),
        allowed_mentions=discord.AllowedMentions.none(),
    )


@gate.command(
    name="dm",
    description="Set or reset the direct message sent to new members.",
)
@app_commands.describe(
    action="Use set or reset.",
    message="Message template to use with set.",
)
async def gate_dm(
    ctx: commands.Context,
    action: str | None = None,
    *,
    message: str | None = None,
) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    if action is None:
        await _show_setting(ctx, "dm_message")
        return
    if action.casefold() == "reset":
        await _set_setting(ctx.bot, ctx.guild.id, "dm_message", None)
        await _enable_if_ready(ctx.bot, ctx.guild.id)
        await ctx.send("The gate join DM has been reset.")
        return
    if action.casefold() != "set":
        await ctx.send("Use `gate dm set <message>` or `gate dm reset`.")
        return
    if message is None:
        await ctx.send("Provide a direct message template.")
        return
    await _set_template(ctx, "dm_message", message)


@gate.command(name="view", description="View the current join/leave message settings.")
async def gate_view(ctx: commands.Context) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    settings = await _load_settings(ctx.bot, ctx.guild.id)
    await ctx.send(
        embed=_settings_embed(ctx.guild, settings),
        allowed_mentions=discord.AllowedMentions.none(),
    )


@gate.command(name="config", description="Edit gate messages in an interactive panel.")
async def gate_config(ctx: commands.Context) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    settings = await _load_settings(ctx.bot, ctx.guild.id)
    view = GateConfigView(ctx, settings)
    view.message = await ctx.send(
        embed=view.build_embed(),
        view=view,
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@gate.command(name="reset", description="Reset all gate settings for this server.")
async def gate_reset(ctx: commands.Context) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    await _database_pool(ctx.bot).execute(
        "DELETE FROM gate_settings WHERE guild_id = $1",
        ctx.guild.id,
    )
    await ctx.send("All gate settings have been reset.")


@gate.command(name="enable", description="Enable join/leave messages.")
async def gate_enable(ctx: commands.Context) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    settings = await _load_settings(ctx.bot, ctx.guild.id)
    if (
        settings is None
        or not any(
            (
                settings["welcome_message"],
                settings["goodbye_message"],
                settings["dm_message"],
            )
        )
    ):
        await ctx.send(
            "Set at least one welcome, goodbye, or DM message before enabling "
            "gate. Welcome and goodbye messages also need a channel."
        )
        return
    if settings["channel_id"] is None and any(
        (settings["welcome_message"], settings["goodbye_message"])
    ):
        await ctx.send(
            "Set a gate channel before enabling welcome or goodbye messages."
        )
        return
    await _set_setting(ctx.bot, ctx.guild.id, "enabled", True)
    await ctx.send("Gate messages are now enabled.")


@gate.command(name="disable", description="Disable join/leave messages.")
async def gate_disable(ctx: commands.Context) -> None:
    if ctx.guild is None:
        await ctx.send("This command can only be used in a server.")
        return
    await _set_setting(ctx.bot, ctx.guild.id, "enabled", False)
    await ctx.send(
        "Gate messages are now disabled."
    )