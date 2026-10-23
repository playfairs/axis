from __future__ import annotations

import json
from typing import Any

from bot.base.imports import commands, discord, logger

EVENT_CATEGORIES: dict[str, tuple[str, dict[str, str]]] = {
    "users": (
        "User updates",
        {
            "user.profile_update": "Username, display name, avatar, banner, and profile changes",
            "member.nickname_update": "Server nickname changes",
            "member.join": "Member joins",
            "member.leave": "Member departures",
        },
    ),
    "messages": (
        "Messages",
        {
            "message.edit": "Message edits with cached before and after content",
            "message.edit_uncached": "Message edits where the original is not cached",
            "message.delete": "Single message deletions",
            "message.bulk_delete": "Bulk message deletions",
            "message.pins_update": "Channel message-pin updates",
        },
    ),
    "guild": (
        "Server settings",
        {
            "guild.name_update": "Server renames",
            "guild.settings_update": "Icon, banner, description, vanity URL, and settings changes",
        },
    ),
    "moderation": (
        "Moderation",
        {
            "member.ban": "Member bans",
            "member.unban": "Member unbans",
            "member.kick": "Member kicks identified in the audit log",
            "member.timeout_add": "Member timeouts",
            "member.timeout_remove": "Timeout removals",
            "member.voice_update": "Server mute, deafen, and voice-state changes",
        },
    ),
    "roles": (
        "Roles",
        {
            "role.create": "Role creation",
            "role.delete": "Role deletion",
            "role.update": "Role name, permissions, color, icon, and position changes",
            "member.roles_update": "Role assignments and removals",
        },
    ),
    "channels": (
        "Channels and webhooks",
        {
            "channel.create": "Channel creation",
            "channel.delete": "Channel deletion",
            "channel.update": "Channel settings, position, category, and overwrites",
            "webhook.create": "Webhook creation identified in audit logs",
            "webhook.update": "Webhook updates identified in audit logs",
            "webhook.delete": "Webhook deletion identified in audit logs",
            "webhook.change_unknown": "Webhook changes that cannot be classified",
        },
    ),
    "community": (
        "Community",
        {
            "invite.create": "Invite creation",
            "invite.delete": "Invite deletion",
            "emoji.update": "Emoji additions, removals, and renames",
            "sticker.update": "Sticker additions, removals, and renames",
            "integration.update": "Integration update notifications",
            "thread.create": "Thread creation",
            "thread.delete": "Thread deletion",
            "thread.update": "Thread setting changes",
            "scheduled_event.create": "Scheduled event creation",
            "scheduled_event.delete": "Scheduled event deletion",
            "scheduled_event.update": "Scheduled event updates",
            "automod.rule_create": "AutoMod rule creation",
            "automod.rule_update": "AutoMod rule updates",
            "automod.rule_delete": "AutoMod rule deletion",
            "automod.action": "AutoMod actions",
        },
    ),
}


def _pool(bot: commands.Bot) -> Any:
    pool = getattr(bot, "database_pool", None)
    if pool is None:
        raise RuntimeError("Modlogs requires the bot's database pool.")
    return pool


async def _load_config(bot: commands.Bot, guild_id: int) -> dict[str, Any]:
    row = await _pool(bot).fetchrow(
        "SELECT config FROM modlog_settings WHERE guild_id = $1",
        guild_id,
    )
    if row is None:
        return {"enabled": False, "categories": {}}
    value = row["config"]
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        logger.warning("Invalid modlogs configuration stored for guild %s.", guild_id)
        return {"enabled": False, "categories": {}}
    value.setdefault("categories", {})
    value.setdefault(
        "enabled",
        any(
            category.get("events")
            for category in value["categories"].values()
            if isinstance(category, dict)
        ),
    )
    return value


async def _save_config(
    bot: commands.Bot,
    guild_id: int,
    config: dict[str, Any],
) -> None:
    await _pool(bot).execute(
        """
        INSERT INTO modlog_settings (guild_id, config)
        VALUES ($1, $2::jsonb)
        ON CONFLICT (guild_id)
        DO UPDATE SET config = EXCLUDED.config, updated_at = NOW()
        """,
        guild_id,
        json.dumps(config),
    )


class _CategorySelect(discord.ui.Select):
    def __init__(self, view: ModlogsConfigView) -> None:
        self.config_view = view
        super().__init__(
            placeholder="Choose a logging category",
            options=[
                discord.SelectOption(
                    label=label,
                    value=key,
                    default=key == view.selected_category,
                )
                for key, (label, _) in EVENT_CATEGORIES.items()
            ],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.config_view.selected_category = self.values[0]
        self.config_view.pending_channel_id = None
        await self.config_view.refresh(interaction)


class _EventSelect(discord.ui.Select):
    def __init__(self, view: ModlogsConfigView) -> None:
        self.config_view = view
        category_config = view._category_config()
        enabled_events = set(category_config.get("events", []))
        events = EVENT_CATEGORIES[view.selected_category][1]
        super().__init__(
            placeholder="Select the event types to log",
            options=[
                discord.SelectOption(
                    label=key.replace(".", " ").replace("_", " ").title(),
                    value=key,
                    description=description[:100],
                    default=key in enabled_events,
                )
                for key, description in events.items()
            ],
            min_values=0,
            max_values=len(events),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        category_config = self.config_view._category_config()
        category_config["events"] = list(self.values)
        await self.config_view.save(interaction)


class _DestinationSelect(discord.ui.ChannelSelect):
    def __init__(self, view: ModlogsConfigView) -> None:
        self.config_view = view
        super().__init__(
            placeholder="Choose a channel for this category",
            channel_types=[
                discord.ChannelType.text,
                discord.ChannelType.news,
                discord.ChannelType.public_thread,
                discord.ChannelType.private_thread,
                discord.ChannelType.news_thread,
            ],
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        selected = self.values[0]
        guild = interaction.guild
        if guild is None or selected.guild_id != guild.id:
            await interaction.response.send_message(
                "Choose a text channel or thread in this server.",
                ephemeral=True,
            )
            return
        channel = guild.get_channel_or_thread(selected.id)
        if channel is None:
            try:
                channel = await self.config_view.bot.fetch_channel(selected.id)
            except discord.NotFound:
                await interaction.response.send_message(
                    "I couldn't find that channel. Please select it again.",
                    ephemeral=True,
                )
                return
            except discord.Forbidden:
                await interaction.response.send_message(
                    "I can't access that channel. Check my server permissions.",
                    ephemeral=True,
                )
                return
            except discord.HTTPException as error:
                logger.warning(
                    "Could not fetch selected modlogs destination %s (HTTP %s).",
                    selected.id,
                    error.status,
                )
                await interaction.response.send_message(
                    "I couldn't verify that channel due to a Discord API error.",
                    ephemeral=True,
                )
                return
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            await interaction.response.send_message(
                "Choose a text channel or thread in this server.",
                ephemeral=True,
            )
            return
        if isinstance(channel, discord.Thread) and (
            channel.archived or channel.locked
        ):
            await interaction.response.send_message(
                "Choose an active, unlocked thread.",
                ephemeral=True,
            )
            return
        bot_member = guild.me
        if bot_member is None:
            await interaction.response.send_message(
                "I couldn't verify my permissions in that channel.",
                ephemeral=True,
            )
            return
        permissions = channel.permissions_for(bot_member)
        can_send = (
            permissions.send_messages_in_threads
            if isinstance(channel, discord.Thread)
            else permissions.send_messages
        )
        if not permissions.view_channel or not can_send:
            await interaction.response.send_message(
                "I need View Channel and permission to send messages there.",
                ephemeral=True,
            )
            return
        self.config_view.pending_channel_id = channel.id
        self.config_view._category_config()["channel_id"] = channel.id
        await self.config_view.save(interaction)


class _ConfigButton(discord.ui.Button):
    def __init__(
        self,
        view: ModlogsConfigView,
        *,
        label: str,
        style: discord.ButtonStyle,
        custom_id: str,
        action: str,
    ) -> None:
        super().__init__(label=label, style=style, custom_id=custom_id)
        self.config_view = view
        self.action = action

    async def callback(self, interaction: discord.Interaction) -> None:
        await getattr(self.config_view, self.action)(interaction)


class ModlogsConfigView(discord.ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        guild: discord.Guild,
        config: dict[str, Any],
        *,
        selected_category: str = "users",
        pending_channel_id: int | None = None,
    ) -> None:
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_id = guild.id
        self.guild = guild
        self.config = config
        self.selected_category = selected_category
        self.pending_channel_id = pending_channel_id
        self._render()

    def _category_config(self) -> dict[str, Any]:
        return self.config.setdefault("categories", {}).setdefault(
            self.selected_category,
            {"events": []},
        )

    def _render(self) -> None:
        category_name = EVENT_CATEGORIES[self.selected_category][0]
        category_config = self._category_config()
        category_channel_id = category_config.get("channel_id")
        shared_channel_id = self.config.get("channel_id")
        active_channel_id = category_channel_id or shared_channel_id
        active_channel = (
            self.guild.get_channel_or_thread(int(active_channel_id))
            if active_channel_id is not None
            else None
        )
        pending_channel = (
            self.guild.get_channel_or_thread(self.pending_channel_id)
            if self.pending_channel_id is not None
            else None
        )
        events = category_config.get("events", [])
        status = (
            "\n".join(f"• `{event}`" for event in events)
            if events
            else "No events enabled for this category."
        )
        destination = (
            f"<#{active_channel_id}>"
            if active_channel_id is not None
            else "Not configured"
        )
        route = "category-specific" if category_channel_id is not None else "shared"
        pending = f"<#{pending_channel.id}>" if pending_channel else "None selected"
        description = (
            f"## Modlogs configuration · {category_name}\n"
            f"**Status:** {'Enabled' if self.config.get('enabled', False) else 'Disabled'}\n\n"
            "Choose event types to log. Selecting a channel applies it to this "
            "category immediately. To use one channel across categories, select "
            "a channel and choose **Set shared channel**. Changes save immediately.\n\n"
            f"**Enabled events**\n{status}\n\n"
            f"**Current destination:** {destination} ({route})\n"
            f"**Selected channel:** {pending}"
        )
        container = discord.ui.Container(
            discord.ui.TextDisplay(description),
            discord.ui.Separator(),
            discord.ui.ActionRow(_CategorySelect(self)),
            discord.ui.ActionRow(_EventSelect(self)),
            discord.ui.ActionRow(_DestinationSelect(self)),
            discord.ui.ActionRow(
                _ConfigButton(
                    self,
                    label="Set shared channel",
                    style=discord.ButtonStyle.primary,
                    custom_id="modlogs:set_shared_channel",
                    action="_set_shared_channel",
                ),
                _ConfigButton(
                    self,
                    label="Use shared channel",
                    style=discord.ButtonStyle.secondary,
                    custom_id="modlogs:use_shared_channel",
                    action="_use_shared_channel",
                ),
                _ConfigButton(
                    self,
                    label="Clear shared channel",
                    style=discord.ButtonStyle.danger,
                    custom_id="modlogs:clear_shared_channel",
                    action="_clear_shared_channel",
                ),
                _ConfigButton(
                    self,
                    label="View Config",
                    style=discord.ButtonStyle.secondary,
                    custom_id="modlogs:view_config",
                    action="_view_config",
                ),
            ),
            accent_color=discord.Colour.blurple(),
        )
        self.clear_items()
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        guild = interaction.guild
        member = interaction.user
        if (
            guild is None
            or guild.id != self.guild_id
            or not isinstance(member, discord.Member)
            or not member.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                "Only server administrators with Manage Server can change modlogs.",
                ephemeral=True,
            )
            return False
        return True

    async def save(self, interaction: discord.Interaction) -> None:
        await _save_config(self.bot, self.guild_id, self.config)
        await self.refresh(interaction)

    async def refresh(self, interaction: discord.Interaction) -> None:
        self._render()
        await interaction.response.edit_message(view=self)

    async def _view_config(self, interaction: discord.Interaction) -> None:
        config = await _load_config(self.bot, self.guild_id)
        lines = [
            "## Current modlogs configuration",
            f"**Logging:** {'Enabled' if config.get('enabled', False) else 'Disabled'}",
        ]
        shared_channel_id = config.get("channel_id")
        shared_destination = (
            f"<#{shared_channel_id}>" if shared_channel_id is not None else "Not set"
        )
        lines.append(f"**Shared destination:** {shared_destination}")

        categories = config.get("categories", {})
        for key, (label, _) in EVENT_CATEGORIES.items():
            category_config = categories.get(key, {})
            if not isinstance(category_config, dict):
                category_config = {}
            channel_id = category_config.get("channel_id", shared_channel_id)
            destination = f"<#{channel_id}>" if channel_id is not None else "Not set"
            events = category_config.get("events", [])
            event_list = ", ".join(f"`{event}`" for event in events) or "None"
            lines.extend(
                (
                    "",
                    f"**{label}**",
                    f"Destination: {destination}",
                    f"Events: {event_list}",
                )
            )

        text = "\n".join(lines)
        if len(text) > 3900:
            text = text[:3899] + "…"
        view = discord.ui.LayoutView(timeout=120)
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(text),
                accent_color=discord.Colour.blurple(),
            )
        )
        await interaction.response.send_message(
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    async def _set_shared_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        if self.pending_channel_id is None:
            await interaction.response.send_message(
                "Choose a channel first.",
                ephemeral=True,
            )
            return
        self.config["channel_id"] = self.pending_channel_id
        await self.save(interaction)

    async def _use_shared_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        self._category_config().pop("channel_id", None)
        await self.save(interaction)

    async def _clear_shared_channel(
        self,
        interaction: discord.Interaction,
    ) -> None:
        self.config.pop("channel_id", None)
        await self.save(interaction)


@commands.group(
    name="modlogs",
    invoke_without_command=True,
    description="Configure server moderation and event logs.",
)
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def modlogs(ctx: commands.Context) -> None:
    if ctx.guild is None:
        return
    await _show_config(ctx)


@modlogs.command(name="config", description="Open the interactive modlogs setup.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def modlogs_config(ctx: commands.Context) -> None:
    await _show_config(ctx)


@modlogs.command(name="enable", description="Enable configured modlogs.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def modlogs_enable(ctx: commands.Context) -> None:
    await _set_modlogs_enabled(ctx, True)


@modlogs.command(name="disable", description="Disable modlogs without removing settings.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def modlogs_disable(ctx: commands.Context) -> None:
    await _set_modlogs_enabled(ctx, False)


@modlogs.command(name="reset", description="Clear modlogs settings and disable logging.")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def modlogs_reset(ctx: commands.Context) -> None:
    if ctx.guild is None:
        return
    await _pool(ctx.bot).execute(
        "DELETE FROM modlog_settings WHERE guild_id = $1",
        ctx.guild.id,
    )
    await ctx.send(
        view=_StatusView("Modlogs settings were reset. Logging is disabled."),
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def _set_modlogs_enabled(ctx: commands.Context, enabled: bool) -> None:
    if ctx.guild is None:
        return
    config = await _load_config(ctx.bot, ctx.guild.id)
    config["enabled"] = enabled
    await _save_config(ctx.bot, ctx.guild.id, config)
    state = "enabled" if enabled else "disabled"
    await ctx.send(
        view=_StatusView(f"Modlogs {state}. Your configuration was preserved."),
        allowed_mentions=discord.AllowedMentions.none(),
    )


class _StatusView(discord.ui.LayoutView):
    def __init__(self, message: str) -> None:
        super().__init__()
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"> {message}"),
                accent_color=discord.Colour.blurple(),
            )
        )


async def _show_config(ctx: commands.Context) -> None:
    if ctx.guild is None:
        return
    config = await _load_config(ctx.bot, ctx.guild.id)
    await ctx.send(
        view=ModlogsConfigView(ctx.bot, ctx.guild, config),
        allowed_mentions=discord.AllowedMentions.none(),
    )


__all__ = ("modlogs",)
