from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from bot.base.imports import commands, discord, logger

SEVERITY_COLORS = {
    "minor": discord.Colour.green(),
    "moderate": discord.Colour.yellow(),
    "major": discord.Colour.red(),
}

SEVERITY_BY_EVENT = {
    "user.profile_update": "minor",
    "member.join": "minor",
    "member.leave": "minor",
    "member.nickname_update": "minor",
    "message.edit": "minor",
    "message.edit_uncached": "minor",
    "message.delete": "minor",
    "message.bulk_delete": "moderate",
    "message.pins_update": "minor",
    "guild.name_update": "major",
    "guild.settings_update": "moderate",
    "member.ban": "major",
    "member.unban": "moderate",
    "member.kick": "major",
    "member.timeout_add": "major",
    "member.timeout_remove": "moderate",
    "member.voice_update": "moderate",
    "role.create": "major",
    "role.delete": "major",
    "role.update": "moderate",
    "member.roles_update": "moderate",
    "channel.create": "major",
    "channel.delete": "major",
    "channel.update": "moderate",
    "webhook.create": "major",
    "webhook.update": "moderate",
    "webhook.delete": "major",
    "webhook.change_unknown": "moderate",
    "invite.create": "moderate",
    "invite.delete": "moderate",
    "emoji.update": "moderate",
    "sticker.update": "moderate",
    "integration.update": "moderate",
    "thread.create": "moderate",
    "thread.delete": "major",
    "thread.update": "moderate",
    "scheduled_event.create": "moderate",
    "scheduled_event.delete": "major",
    "scheduled_event.update": "moderate",
    "automod.rule_create": "major",
    "automod.rule_update": "moderate",
    "automod.rule_delete": "major",
    "automod.action": "moderate",
}


def _display(value: object, *, limit: int = 900) -> str:
    if value is None:
        result = "None"
    elif isinstance(value, datetime):
        result = discord.utils.format_dt(value, style="F")
    else:
        result = str(value)
    if len(result) > limit:
        return result[: limit - 1] + "…"
    return result


def _entity_label(target: object | None) -> str:
    if target is None:
        return "Unknown"
    name = getattr(target, "display_name", None) or getattr(target, "name", None)
    target_id = getattr(target, "id", None)
    if name is None:
        return _display(target)
    if target_id is None:
        return _display(name)
    return f"{_display(name)} (`{target_id}`)"


def _change_lines(
    before: object,
    after: object,
    fields: tuple[tuple[str, str], ...],
) -> list[str]:
    changes: list[str] = []
    for attribute, label in fields:
        old_value = getattr(before, attribute, None)
        new_value = getattr(after, attribute, None)
        old_value = getattr(old_value, "value", old_value)
        new_value = getattr(new_value, "value", new_value)
        if attribute == "features":
            old_value = sorted(old_value or [])
            new_value = sorted(new_value or [])
        if old_value != new_value:
            changes.append(
                f"**{label}:** `{_display(old_value)}` → `{_display(new_value)}`"
            )
    return changes


def _permission_names(permissions: discord.Permissions) -> list[str]:
    labels = {"read_messages": "View Channel"}
    return [
        labels.get(name, name.replace("_", " ").title())
        for name, enabled in permissions
        if enabled
    ]


def _role_permission_details(
    before: discord.Permissions,
    after: discord.Permissions,
) -> list[str]:
    before_names = set(_permission_names(before))
    after_names = set(_permission_names(after))
    added = sorted(after_names - before_names)
    removed = sorted(before_names - after_names)
    if before.value == after.value:
        return []

    details = [
        f"**Permission bitfield:** `{before.value}` → `{after.value}`",
    ]
    if added:
        details.append(
            "**Permissions added:** " + ", ".join(f"`{name}`" for name in added)
        )
    if removed:
        details.append(
            "**Permissions removed:** "
            + ", ".join(f"`{name}`" for name in removed)
        )
    return details


async def _event_enabled(
    bot: commands.Bot,
    guild_id: int,
    category: str,
    event: str,
) -> bool:
    pool = getattr(bot, "database_pool", None)
    if pool is None:
        return False
    row = await pool.fetchrow(
        "SELECT config FROM modlog_settings WHERE guild_id = $1",
        guild_id,
    )
    if row is None:
        return False
    config = row["config"]
    if isinstance(config, str):
        config = json.loads(config)
    categories = config.get("categories", {})
    category_config = categories.get(category, {})
    configured_events = (
        event
        for value in categories.values()
        if isinstance(value, dict)
        for event in value.get("events", [])
    )
    enabled = config.get("enabled", any(configured_events))
    return (
        enabled
        and event in category_config.get("events", [])
        and category_config.get("channel_id", config.get("channel_id")) is not None
    )


async def _find_audit_entry(
    bot: commands.Bot,
    guild: discord.Guild,
    action_name: str,
    target_id: int | None,
    *,
    category: str,
    event: str,
    channel_id: int | None = None,
    change_fields: set[str] | None = None,
) -> discord.AuditLogEntry | None:
    if not await _event_enabled(bot, guild.id, category, event):
        return None
    action = getattr(discord.AuditLogAction, action_name, None)
    if action is None:
        return None
    now = discord.utils.utcnow()
    try:
        async for entry in guild.audit_logs(limit=8, action=action):
            if (
                target_id is not None
                and getattr(entry.target, "id", None) != target_id
            ):
                continue
            age = (now - entry.created_at).total_seconds()
            if not -3 <= age <= 10:
                continue
            if channel_id is not None:
                extra = entry.extra
                audit_channel_id = getattr(extra, "channel_id", None)
                audit_channel = getattr(extra, "channel", None)
                if audit_channel_id is None and audit_channel is not None:
                    audit_channel_id = getattr(audit_channel, "id", None)
                if audit_channel_id != channel_id:
                    continue
            if change_fields is not None:
                changes = entry.changes
                recorded_fields = set(changes.before.__dict__) | set(
                    changes.after.__dict__
                )
                if not change_fields.intersection(recorded_fields):
                    continue
            return entry
    except discord.Forbidden:
        logger.debug("Cannot read audit log for guild %s.", guild.id)
    except discord.HTTPException as error:
        logger.warning(
            "Could not read audit log for guild %s (HTTP %s).",
            guild.id,
            error.status,
        )
    return None


async def _find_bulk_delete_audit_entry(
    bot: commands.Bot,
    guild: discord.Guild,
    count: int,
) -> discord.AuditLogEntry | None:
    if not await _event_enabled(bot, guild.id, "messages", "message.bulk_delete"):
        return None
    action = discord.AuditLogAction.message_bulk_delete
    now = discord.utils.utcnow()
    matches: list[discord.AuditLogEntry] = []
    try:
        async for entry in guild.audit_logs(limit=8, action=action):
            age = (now - entry.created_at).total_seconds()
            if (
                -3 <= age <= 10
                and getattr(entry.extra, "count", None) == count
            ):
                matches.append(entry)
    except discord.Forbidden:
        logger.debug("Cannot read audit log for guild %s.", guild.id)
    except discord.HTTPException as error:
        logger.warning(
            "Could not read audit log for guild %s (HTTP %s).",
            guild.id,
            error.status,
        )
    return matches[0] if len(matches) == 1 else None


async def _log(
    bot: commands.Bot,
    guild: discord.Guild,
    *,
    category: str,
    event: str,
    action: str,
    target: str,
    details: list[str] | None = None,
    severity: str | None = None,
    executor: discord.User | discord.Member | None = None,
    reason: str | None = None,
    timestamp: datetime | None = None,
) -> None:
    pool = getattr(bot, "database_pool", None)
    if pool is None:
        return
    row = await pool.fetchrow(
        "SELECT config FROM modlog_settings WHERE guild_id = $1",
        guild.id,
    )
    if row is None:
        return
    config = row["config"]
    if isinstance(config, str):
        config = json.loads(config)
    categories = config.get("categories", {})
    configured_events = (
        event_name
        for value in categories.values()
        if isinstance(value, dict)
        for event_name in value.get("events", [])
    )
    if not config.get("enabled", any(configured_events)):
        return
    category_config = categories.get(category, {})
    enabled_events = category_config.get("events", [])
    if event not in enabled_events:
        return

    channel_id = category_config.get("channel_id", config.get("channel_id"))
    if channel_id is None:
        logger.warning(
            "Modlogs event %s is enabled for guild %s without a destination.",
            event,
            guild.id,
        )
        return
    channel = guild.get_channel_or_thread(int(channel_id))
    destination_types = (discord.TextChannel, discord.Thread)
    if isinstance(channel, destination_types) and channel.guild.id != guild.id:
        logger.warning(
            "Configured modlogs channel %s belongs to a different guild.",
            channel_id,
        )
        return
    if not isinstance(channel, destination_types):
        try:
            fetched_channel = await bot.fetch_channel(int(channel_id))
        except discord.NotFound:
            logger.warning(
                "Configured modlogs channel %s no longer exists in guild %s.",
                channel_id,
                guild.id,
            )
            return
        except discord.Forbidden:
            logger.warning(
                "Cannot access configured modlogs channel %s in guild %s.",
                channel_id,
                guild.id,
            )
            return
        except discord.HTTPException as error:
            logger.warning(
                "Could not fetch modlogs channel %s (HTTP %s).",
                channel_id,
                error.status,
            )
            return
        if (
            not isinstance(fetched_channel, destination_types)
            or fetched_channel.guild.id != guild.id
        ):
            logger.warning(
                "Configured modlogs destination %s is not a text channel or thread.",
                channel_id,
            )
            return
        channel = fetched_channel

    if isinstance(channel, discord.Thread) and (channel.archived or channel.locked):
        logger.warning(
            "Configured modlogs thread %s is archived or locked.",
            channel.id,
        )
        return

    occurred_at = timestamp or discord.utils.utcnow()
    lines = [
        f"**Executor:** {_entity_label(executor) if executor else 'Unknown (not available)'}",
        f"**Target:** {target}",
        f"**Time:** {discord.utils.format_dt(occurred_at, style='F')}",
    ]
    if reason is not None:
        lines.append(f"**Reason:** {_display(reason)}")
    if details:
        lines.extend(details)
    body = "\n".join(lines)
    if len(body) > 3800:
        body = body[:3799] + "…"

    view = discord.ui.LayoutView(timeout=None)
    severity = SEVERITY_BY_EVENT.get(event, severity or "moderate")
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(f"## {action}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(body),
            accent_color=SEVERITY_COLORS[severity],
        )
    )
    try:
        await channel.send(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.Forbidden:
        logger.warning(
            "Missing permission to send modlogs to channel %s.",
            channel.id,
        )
    except discord.HTTPException as error:
        logger.warning(
            "Could not send modlogs to channel %s (HTTP %s).",
            channel.id,
            error.status,
        )


async def on_user_update(
    bot: commands.Bot,
    before: discord.User,
    after: discord.User,
) -> None:
    changes = _change_lines(
        before,
        after,
        (
            ("name", "Username"),
            ("global_name", "Display name"),
            ("avatar", "Avatar"),
            ("banner", "Banner"),
            ("accent_color", "Profile color"),
            ("avatar_decoration", "Avatar decoration"),
            ("primary_guild", "Primary guild"),
            ("public_flags", "Public account flags"),
            ("discriminator", "Legacy discriminator"),
        ),
    )
    if not changes:
        return
    for guild in bot.guilds:
        if guild.get_member(after.id) is not None:
            await _log(
                bot,
                guild,
                category="users",
                event="user.profile_update",
                action="User profile updated",
                target=_entity_label(after),
                details=changes,
                severity="minor",
            )


async def on_member_update(
    bot: commands.Bot,
    before: discord.Member,
    after: discord.Member,
) -> None:
    if before.nick != after.nick:
        entry = await _find_audit_entry(
            bot,
            after.guild,
            "member_update",
            after.id,
            category="users",
            event="member.nickname_update",
            change_fields={"nick"},
        )
        await _log(
            bot,
            after.guild,
            category="users",
            event="member.nickname_update",
            action="Nickname changed",
            target=_entity_label(after),
            details=[
                f"**Before:** {_display(before.nick)}",
                f"**After:** {_display(after.nick)}",
            ],
            severity="minor",
            executor=entry.user if entry else None,
            reason=entry.reason if entry else None,
            timestamp=entry.created_at if entry else None,
        )

    before_roles = {role.id: role for role in before.roles}
    after_roles = {role.id: role for role in after.roles}
    added = [role for role_id, role in after_roles.items() if role_id not in before_roles]
    removed = [role for role_id, role in before_roles.items() if role_id not in after_roles]
    if added or removed:
        entry = await _find_audit_entry(
            bot,
            after.guild,
            "member_role_update",
            after.id,
            category="roles",
            event="member.roles_update",
        )
        details = []
        if added:
            details.append("**Added:** " + ", ".join(_entity_label(role) for role in added))
        if removed:
            details.append(
                "**Removed:** " + ", ".join(_entity_label(role) for role in removed)
            )
        await _log(
            bot,
            after.guild,
            category="roles",
            event="member.roles_update",
            action="Member roles changed",
            target=_entity_label(after),
            details=details,
            severity="moderate",
            executor=entry.user if entry else None,
            reason=entry.reason if entry else None,
            timestamp=entry.created_at if entry else None,
        )

    if before.timed_out_until != after.timed_out_until:
        active = after.timed_out_until is not None
        entry = await _find_audit_entry(
            bot,
            after.guild,
            "member_update",
            after.id,
            category="moderation",
            event="member.timeout_add" if active else "member.timeout_remove",
            change_fields={"timed_out_until"},
        )
        await _log(
            bot,
            after.guild,
            category="moderation",
            event="member.timeout_add" if active else "member.timeout_remove",
            action="Member timed out" if active else "Member timeout removed",
            target=_entity_label(after),
            details=[
                f"**Before:** {_display(before.timed_out_until)}",
                f"**After:** {_display(after.timed_out_until)}",
            ],
            severity="major" if active else "moderate",
            executor=entry.user if entry else None,
            reason=entry.reason if entry else None,
            timestamp=entry.created_at if entry else None,
        )


async def on_member_join(bot: commands.Bot, member: discord.Member) -> None:
    await _log(
        bot,
        member.guild,
        category="users",
        event="member.join",
        action="Member joined",
        target=_entity_label(member),
        details=[f"**Account created:** {_display(member.created_at)}"],
        severity="minor",
    )


async def on_message_edit(
    bot: commands.Bot,
    before: discord.Message,
    after: discord.Message,
) -> None:
    if before.guild is None or before.content == after.content:
        return
    await _log(
        bot,
        before.guild,
        category="messages",
        event="message.edit",
        action="Message edited",
        target=f"[Jump to message]({after.jump_url}) by {_entity_label(after.author)}",
        details=[
            f"**Before:**\n```{_display(before.content or '[No cached content]')}```",
            f"**After:**\n```{_display(after.content or '[No content]')}```",
        ],
        severity="minor",
        timestamp=after.edited_at or discord.utils.utcnow(),
    )


async def on_raw_message_edit(
    bot: commands.Bot,
    payload: discord.RawMessageUpdateEvent,
) -> None:
    if payload.cached_message is not None or payload.guild_id is None:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    after = payload.message
    content = payload.data.get("content")
    if content is None:
        content = "[Updated content unavailable in the gateway payload]"
    await _log(
        bot,
        guild,
        category="messages",
        event="message.edit_uncached",
        action="Message edited (original not cached)",
        target=f"[Jump to message]({after.jump_url}) by {_entity_label(after.author)}",
        details=[
            "**Before:** [Original message was not cached]",
            f"**After:**\n```{_display(content)}```",
        ],
        severity="minor",
        timestamp=after.edited_at or discord.utils.utcnow(),
    )


async def on_raw_message_delete(
    bot: commands.Bot,
    payload: discord.RawMessageDeleteEvent,
) -> None:
    if payload.guild_id is None:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    cached = payload.cached_message
    entry = (
        await _find_audit_entry(
            bot,
            guild,
            "message_delete",
            cached.author.id,
            category="messages",
            event="message.delete",
            channel_id=payload.channel_id,
        )
        if cached is not None
        else None
    )
    details = [
        f"**Channel:** <#{payload.channel_id}>",
        f"**Message ID:** `{payload.message_id}`",
        f"**Content:**\n```{_display(cached.content if cached else '[Not cached]')}```",
    ]
    await _log(
        bot,
        guild,
        category="messages",
        event="message.delete",
        action="Message deleted",
        target=_entity_label(cached.author) if cached else f"Unknown (`{payload.message_id}`)",
        details=details,
        severity="minor",
        executor=entry.user if entry else cached.author if cached else None,
        reason=entry.reason if entry else None,
        timestamp=entry.created_at if entry else None,
    )


async def on_raw_bulk_message_delete(
    bot: commands.Bot,
    payload: discord.RawBulkMessageDeleteEvent,
) -> None:
    if payload.guild_id is None:
        return
    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return
    count = len(payload.message_ids)
    entry = await _find_bulk_delete_audit_entry(bot, guild, count)
    cached_details = [
        f"• {_entity_label(message.author)}: `{_display(message.content, limit=250)}`"
        for message in payload.cached_messages[:10]
    ]
    if len(payload.cached_messages) > len(cached_details):
        cached_details.append(
            f"…and {len(payload.cached_messages) - len(cached_details)} more cached messages"
        )
    message_ids = sorted(payload.message_ids)
    details = [
        "**Message IDs:** "
        + ", ".join(f"`{message_id}`" for message_id in message_ids[:20])
    ]
    if cached_details:
        details.append("**Cached messages:**\n" + "\n".join(cached_details))
    await _log(
        bot,
        guild,
        category="messages",
        event="message.bulk_delete",
        action="Messages bulk deleted",
        target=f"{count} messages in <#{payload.channel_id}>",
        details=details,
        severity="moderate",
        executor=entry.user if entry else None,
        reason=entry.reason if entry else None,
        timestamp=entry.created_at if entry else None,
    )


async def on_guild_channel_pins_update(
    bot: commands.Bot,
    channel: discord.abc.GuildChannel,
    last_pin: datetime | None,
) -> None:
    await _log(
        bot,
        channel.guild,
        category="messages",
        event="message.pins_update",
        action="Channel message pins updated",
        target=_entity_label(channel),
        details=[
            "**Latest pin timestamp:** "
            f"{_display(last_pin)}",
            "Discord does not distinguish a pin from an unpin in this event.",
        ],
        severity="minor",
    )


async def on_member_ban(
    bot: commands.Bot,
    guild: discord.Guild,
    user: discord.User,
) -> None:
    entry = await _find_audit_entry(
        bot,
        guild,
        "ban",
        user.id,
        category="moderation",
        event="member.ban",
    )
    await _log(
        bot,
        guild,
        category="moderation",
        event="member.ban",
        action="Member banned",
        target=_entity_label(user),
        severity="major",
        executor=entry.user if entry else None,
        reason=entry.reason if entry else None,
        timestamp=entry.created_at if entry else None,
    )


async def on_member_unban(
    bot: commands.Bot,
    guild: discord.Guild,
    user: discord.User,
) -> None:
    entry = await _find_audit_entry(
        bot,
        guild,
        "unban",
        user.id,
        category="moderation",
        event="member.unban",
    )
    await _log(
        bot,
        guild,
        category="moderation",
        event="member.unban",
        action="Member unbanned",
        target=_entity_label(user),
        severity="moderate",
        executor=entry.user if entry else None,
        reason=entry.reason if entry else None,
        timestamp=entry.created_at if entry else None,
    )


async def on_member_remove(
    bot: commands.Bot,
    member: discord.Member,
) -> None:
    log_kicks = await _event_enabled(
        bot,
        member.guild.id,
        "moderation",
        "member.kick",
    )
    log_departures = await _event_enabled(
        bot,
        member.guild.id,
        "users",
        "member.leave",
    )
    audit_category = "moderation" if log_kicks else "users"
    audit_event = "member.kick" if log_kicks else "member.leave"
    entry = (
        await _find_audit_entry(
            bot,
            member.guild,
            "kick",
            member.id,
            category=audit_category,
            event=audit_event,
        )
        if log_kicks or log_departures
        else None
    )
    if entry is not None:
        if log_kicks:
            await _log(
                bot,
                member.guild,
                category="moderation",
                event="member.kick",
                action="Member kicked",
                target=_entity_label(member),
                severity="major",
                executor=entry.user,
                reason=entry.reason,
                timestamp=entry.created_at,
            )
        elif log_departures:
            await _log(
                bot,
                member.guild,
                category="users",
                event="member.leave",
                action="Member departed (kick confirmed)",
                target=_entity_label(member),
                details=["This departure was identified as a kick in the audit log."],
                executor=entry.user,
                reason=entry.reason,
                timestamp=entry.created_at,
            )
        return

    ban_entry = await _find_audit_entry(
        bot,
        member.guild,
        "ban",
        member.id,
        category="users",
        event="member.leave",
    )
    if ban_entry is None:
        await _log(
            bot,
            member.guild,
            category="users",
            event="member.leave",
            action="Member departed",
            target=_entity_label(member),
            details=["No matching kick or ban audit-log entry was available."],
            severity="minor",
        )


async def on_voice_state_update(
    bot: commands.Bot,
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    fields = (
        ("mute", "Server muted"),
        ("deaf", "Server deafened"),
        ("self_mute", "Self muted"),
        ("self_deaf", "Self deafened"),
        ("suppress", "Stage suppressed"),
    )
    changes = [
        f"**{label}:** `{getattr(before, attribute)}` → `{getattr(after, attribute)}`"
        for attribute, label in fields
        if getattr(before, attribute) != getattr(after, attribute)
    ]
    if changes:
        server_voice_change = before.mute != after.mute or before.deaf != after.deaf
        entry = (
            await _find_audit_entry(
                bot,
                member.guild,
                "member_update",
                member.id,
                category="moderation",
                event="member.voice_update",
                change_fields={"mute", "deaf"},
            )
            if server_voice_change
            else None
        )
        await _log(
            bot,
            member.guild,
            category="moderation",
            event="member.voice_update",
            action="Voice state changed",
            target=_entity_label(member),
            details=changes,
            severity="moderate",
            executor=entry.user if entry else None,
            reason=entry.reason if entry else None,
            timestamp=entry.created_at if entry else None,
        )


async def on_guild_update(
    bot: commands.Bot,
    before: discord.Guild,
    after: discord.Guild,
) -> None:
    name_change = before.name != after.name
    fields = (
        ("icon", "Icon"),
        ("banner", "Banner"),
        ("splash", "Invite splash"),
        ("discovery_splash", "Discovery splash"),
        ("description", "Description"),
        ("tag", "Guild tag"),
        ("vanity_url_code", "Vanity URL"),
        ("verification_level", "Verification level"),
        ("default_notifications", "Default notifications"),
        ("explicit_content_filter", "Explicit content filter"),
        ("mfa_level", "MFA level"),
        ("features", "Features"),
        ("preferred_locale", "Preferred locale"),
        ("afk_timeout", "AFK timeout"),
        ("afk_channel_id", "AFK channel"),
        ("system_channel_id", "System channel"),
        ("rules_channel_id", "Rules channel"),
        ("public_updates_channel_id", "Public updates channel"),
        ("safety_alerts_channel_id", "Safety alerts channel"),
        ("widget_enabled", "Server widget"),
        ("widget_channel_id", "Widget channel"),
        ("max_presences", "Presence limit"),
        ("max_members", "Member limit"),
        ("max_video_channel_users", "Video channel user limit"),
        ("premium_tier", "Boost tier"),
        ("premium_subscription_count", "Boost count"),
        ("premium_progress_bar_enabled", "Boost progress bar"),
        ("nsfw_level", "NSFW level"),
    )
    changes = _change_lines(before, after, fields)
    audit_event = None
    if name_change and await _event_enabled(
        bot,
        after.id,
        "guild",
        "guild.name_update",
    ):
        audit_event = "guild.name_update"
    elif changes and await _event_enabled(
        bot,
        after.id,
        "guild",
        "guild.settings_update",
    ):
        audit_event = "guild.settings_update"
    entry = (
        await _find_audit_entry(
            bot,
            after,
            "guild_update",
            after.id,
            category="guild",
            event=audit_event,
        )
        if audit_event is not None
        else None
    )
    if name_change:
        await _log(
            bot,
            after,
            category="guild",
            event="guild.name_update",
            action="Server renamed",
            target=f"{_display(before.name)} → {_display(after.name)}",
            severity="major",
            executor=entry.user if entry else None,
            reason=entry.reason if entry else None,
            timestamp=entry.created_at if entry else None,
        )
    if changes:
        await _log(
            bot,
            after,
            category="guild",
            event="guild.settings_update",
            action="Server settings changed",
            target=_entity_label(after),
            details=changes,
            severity="moderate",
            executor=entry.user if entry else None,
            reason=entry.reason if entry else None,
            timestamp=entry.created_at if entry else None,
        )


async def on_guild_role_create(bot: commands.Bot, role: discord.Role) -> None:
    entry = await _find_audit_entry(
        bot,
        role.guild,
        "role_create",
        role.id,
        category="roles",
        event="role.create",
    )
    await _log(
        bot,
        role.guild,
        category="roles",
        event="role.create",
        action="Role created",
        target=_entity_label(role),
        details=[
            f"**Permission bitfield:** `{role.permissions.value}`",
            "**Permissions:** "
            + (
                ", ".join(f"`{name}`" for name in _permission_names(role.permissions))
                or "None"
            ),
        ],
        severity="major",
        executor=entry.user if entry else None,
        reason=entry.reason if entry else None,
        timestamp=entry.created_at if entry else None,
    )


async def on_guild_role_delete(bot: commands.Bot, role: discord.Role) -> None:
    entry = await _find_audit_entry(
        bot,
        role.guild,
        "role_delete",
        role.id,
        category="roles",
        event="role.delete",
    )
    await _log(
        bot,
        role.guild,
        category="roles",
        event="role.delete",
        action="Role deleted",
        target=_entity_label(role),
        details=[f"**Permissions:** `{role.permissions.value}`"],
        severity="major",
        executor=entry.user if entry else None,
        reason=entry.reason if entry else None,
        timestamp=entry.created_at if entry else None,
    )


async def on_guild_role_update(
    bot: commands.Bot,
    before: discord.Role,
    after: discord.Role,
) -> None:
    changes = _change_lines(
        before,
        after,
        (
            ("name", "Name"),
            ("colour", "Color"),
            ("hoist", "Displayed separately"),
            ("mentionable", "Mentionable"),
            ("position", "Position"),
            ("icon", "Icon"),
        ),
    )
    changes.extend(
        _role_permission_details(before.permissions, after.permissions)
    )
    if not changes:
        return
    entry = await _find_audit_entry(
        bot,
        after.guild,
        "role_update",
        after.id,
        category="roles",
        event="role.update",
    )
    bot_member = after.guild.me
    if entry is None and bot_member is not None:
        if bot_member.guild_permissions.view_audit_log:
            logger.debug(
                "Ignoring role update for %s in guild %s without a recent "
                "matching audit-log entry.",
                after.id,
                after.guild.id,
            )
            return
    await _log(
        bot,
        after.guild,
        category="roles",
        event="role.update",
        action="Role updated",
        target=_entity_label(after),
        details=changes,
        severity="moderate",
        executor=entry.user if entry else None,
        reason=entry.reason if entry else None,
        timestamp=entry.created_at if entry else None,
    )


async def on_guild_channel_create(
    bot: commands.Bot,
    channel: discord.abc.GuildChannel,
) -> None:
    entry = await _find_audit_entry(
        bot,
        channel.guild,
        "channel_create",
        channel.id,
        category="channels",
        event="channel.create",
    )
    await _log(
        bot,
        channel.guild,
        category="channels",
        event="channel.create",
        action="Channel created",
        target=_entity_label(channel),
        details=[f"**Type:** `{channel.type}`"],
        severity="major",
        executor=entry.user if entry else None,
        reason=entry.reason if entry else None,
        timestamp=entry.created_at if entry else None,
    )


async def on_guild_channel_delete(
    bot: commands.Bot,
    channel: discord.abc.GuildChannel,
) -> None:
    entry = await _find_audit_entry(
        bot,
        channel.guild,
        "channel_delete",
        channel.id,
        category="channels",
        event="channel.delete",
    )
    await _log(
        bot,
        channel.guild,
        category="channels",
        event="channel.delete",
        action="Channel deleted",
        target=_entity_label(channel),
        details=[f"**Type:** `{channel.type}`"],
        severity="major",
        executor=entry.user if entry else None,
        reason=entry.reason if entry else None,
        timestamp=entry.created_at if entry else None,
    )


async def on_guild_channel_update(
    bot: commands.Bot,
    before: discord.abc.GuildChannel,
    after: discord.abc.GuildChannel,
) -> None:
    fields = (
        ("name", "Name"),
        ("topic", "Topic"),
        ("nsfw", "NSFW"),
        ("slowmode_delay", "Slowmode"),
        ("bitrate", "Bitrate"),
        ("user_limit", "User limit"),
        ("rtc_region", "RTC region"),
        ("video_quality_mode", "Video quality"),
        ("default_auto_archive_duration", "Default thread archive duration"),
        ("default_thread_slowmode_delay", "Default thread slowmode"),
        ("default_sort_order", "Default sort order"),
        ("default_reaction_emoji", "Default reaction"),
        ("available_tags", "Forum tags"),
        ("position", "Position"),
        ("category_id", "Category"),
        ("permissions_synced", "Permissions synced"),
    )
    changes = _change_lines(before, after, fields)
    before_overwrites = getattr(before, "overwrites", None)
    after_overwrites = getattr(after, "overwrites", None)
    if before_overwrites != after_overwrites:
        overwrite_changes = []
        all_targets = set(before_overwrites or {}) | set(after_overwrites or {})
        for target in all_targets:
            old = (before_overwrites or {}).get(target)
            new = (after_overwrites or {}).get(target)
            no_permissions = (discord.Permissions.none(), discord.Permissions.none())
            old_pair = old.pair() if old is not None else no_permissions
            new_pair = new.pair() if new is not None else no_permissions
            if old_pair != new_pair:
                overwrite_changes.append(
                    f"• {_entity_label(target)}: "
                    f"`allow {old_pair[0].value}/deny {old_pair[1].value}` → "
                    f"`allow {new_pair[0].value}/deny {new_pair[1].value}`"
                )
        changes.append(
            "**Permission overwrites:**\n"
            + "\n".join(overwrite_changes[:15])
        )
    if not changes:
        return
    entry = await _find_audit_entry(
        bot,
        after.guild,
        "channel_update",
        after.id,
        category="channels",
        event="channel.update",
    )
    await _log(
        bot,
        after.guild,
        category="channels",
        event="channel.update",
        action="Channel settings changed",
        target=_entity_label(after),
        details=changes,
        severity="moderate",
        executor=entry.user if entry else None,
        reason=entry.reason if entry else None,
        timestamp=entry.created_at if entry else None,
    )


async def on_webhooks_update(
    bot: commands.Bot,
    channel: discord.abc.GuildChannel,
) -> None:
    webhook_actions = {
        "webhook_create": ("webhook.create", "Webhook created", "major"),
        "webhook_update": ("webhook.update", "Webhook updated", "moderate"),
        "webhook_delete": ("webhook.delete", "Webhook deleted", "major"),
    }
    enabled_events = {
        event_details[0]
        for event_details in webhook_actions.values()
        if await _event_enabled(
            bot,
            channel.guild.id,
            "channels",
            event_details[0],
        )
    }
    unknown_enabled = await _event_enabled(
        bot,
        channel.guild.id,
        "channels",
        "webhook.change_unknown",
    )
    if not enabled_events:
        if unknown_enabled:
            await _log(
                bot,
                channel.guild,
                category="channels",
                event="webhook.change_unknown",
                action="Webhooks changed",
                target=_entity_label(channel),
                details=[
                    "No matching audit-log entry was available to classify "
                    "the webhook change."
                ],
            )
        return

    now = discord.utils.utcnow()
    try:
        async for entry in channel.guild.audit_logs(limit=10):
            event_details = webhook_actions.get(entry.action.name)
            if event_details is None:
                continue
            age = (now - entry.created_at).total_seconds()
            if not -3 <= age <= 10:
                continue
            changes = entry.changes
            changed_channel = getattr(changes.after, "channel", None)
            if changed_channel is None:
                changed_channel = getattr(changes.before, "channel", None)
            if getattr(changed_channel, "id", None) != channel.id:
                continue
            if event_details[0] not in enabled_events:
                return
            seen_entries = getattr(bot, "_modlogs_seen_webhook_audit_ids", None)
            if seen_entries is None:
                seen_entries = set()
                setattr(bot, "_modlogs_seen_webhook_audit_ids", seen_entries)
            if entry.id in seen_entries:
                return
            seen_entries.add(entry.id)
            if len(seen_entries) > 512:
                seen_entries.pop()
            event, action, severity = event_details
            before_values = changes.before.__dict__
            after_values = changes.after.__dict__
            details = [
                f"**{field.replace('_', ' ').title()}:** "
                f"`{_display(before_values.get(field))}` → "
                f"`{_display(after_values.get(field))}`"
                for field in before_values.keys() | after_values.keys()
            ]
            await _log(
                bot,
                channel.guild,
                category="channels",
                event=event,
                action=action,
                target=f"Webhook `{getattr(entry.target, 'id', 'unknown')}`",
                details=details or [f"**Channel:** {_entity_label(channel)}"],
                severity=severity,
                executor=entry.user,
                reason=entry.reason,
                timestamp=entry.created_at,
            )
            return
    except discord.Forbidden:
        logger.debug(
            "Cannot read webhook audit logs for guild %s.",
            channel.guild.id,
        )
    except discord.HTTPException as error:
        logger.warning(
            "Could not read webhook audit logs for guild %s (HTTP %s).",
            channel.guild.id,
            error.status,
        )

    if unknown_enabled:
        await _log(
            bot,
            channel.guild,
            category="channels",
            event="webhook.change_unknown",
            action="Webhooks changed",
            target=_entity_label(channel),
            details=[
                "Discord signaled a webhook change, but the matching audit-log "
                "entry was unavailable."
            ],
            severity="moderate",
        )


async def on_invite_create(bot: commands.Bot, invite: discord.Invite) -> None:
    if invite.guild is None:
        return
    await _log(
        bot,
        invite.guild,
        category="community",
        event="invite.create",
        action="Invite created",
        target=f"`{invite.code}`",
        details=[
            f"**Channel:** {_entity_label(invite.channel)}",
            f"**Inviter:** {_entity_label(invite.inviter)}",
            f"**Expires:** {_display(invite.expires_at)}",
        ],
        severity="moderate",
        executor=invite.inviter,
    )


async def on_invite_delete(bot: commands.Bot, invite: discord.Invite) -> None:
    if invite.guild is None:
        return
    await _log(
        bot,
        invite.guild,
        category="community",
        event="invite.delete",
        action="Invite deleted",
        target=f"`{invite.code}`",
        details=[f"**Channel:** {_entity_label(invite.channel)}"],
        severity="moderate",
    )


async def on_guild_emojis_update(
    bot: commands.Bot,
    guild: discord.Guild,
    before: list[discord.Emoji],
    after: list[discord.Emoji],
) -> None:
    old = {emoji.id: emoji for emoji in before}
    new = {emoji.id: emoji for emoji in after}
    added = [emoji for emoji_id, emoji in new.items() if emoji_id not in old]
    removed = [emoji for emoji_id, emoji in old.items() if emoji_id not in new]
    changed = [
        f"`{old[emoji_id].name}` → `{new[emoji_id].name}`"
        for emoji_id in old.keys() & new.keys()
        if old[emoji_id].name != new[emoji_id].name
    ]
    details = []
    if added:
        details.append("**Added:** " + ", ".join(_display(emoji) for emoji in added))
    if removed:
        details.append("**Removed:** " + ", ".join(_display(emoji) for emoji in removed))
    if changed:
        details.append("**Renamed:** " + ", ".join(changed))
    if details:
        await _log(
            bot,
            guild,
            category="community",
            event="emoji.update",
            action="Server emoji changed",
            target=f"{len(added)} added, {len(removed)} removed, {len(changed)} renamed",
            details=details,
            severity="moderate",
        )


async def on_guild_stickers_update(
    bot: commands.Bot,
    guild: discord.Guild,
    before: list[discord.GuildSticker],
    after: list[discord.GuildSticker],
) -> None:
    old = {sticker.id: sticker for sticker in before}
    new = {sticker.id: sticker for sticker in after}
    added = [sticker for sticker_id, sticker in new.items() if sticker_id not in old]
    removed = [sticker for sticker_id, sticker in old.items() if sticker_id not in new]
    changed = [
        f"`{old[sticker_id].name}` → `{new[sticker_id].name}`"
        for sticker_id in old.keys() & new.keys()
        if old[sticker_id].name != new[sticker_id].name
    ]
    details = []
    if added:
        details.append("**Added:** " + ", ".join(_display(sticker) for sticker in added))
    if removed:
        details.append("**Removed:** " + ", ".join(_display(sticker) for sticker in removed))
    if changed:
        details.append("**Renamed:** " + ", ".join(changed))
    if details:
        await _log(
            bot,
            guild,
            category="community",
            event="sticker.update",
            action="Server sticker changed",
            target=f"{len(added)} added, {len(removed)} removed, {len(changed)} renamed",
            details=details,
            severity="moderate",
        )


async def on_guild_integrations_update(
    bot: commands.Bot,
    guild: discord.Guild,
) -> None:
    await _log(
        bot,
        guild,
        category="community",
        event="integration.update",
        action="Integrations changed",
        target=_entity_label(guild),
        details=[
            "Discord reports an integration update; individual changes are "
            "unavailable from this gateway event."
        ],
        severity="moderate",
    )


async def on_thread_create(
    bot: commands.Bot,
    thread: discord.Thread,
) -> None:
    entry = await _find_audit_entry(
        bot,
        thread.guild,
        "thread_create",
        thread.id,
        category="community",
        event="thread.create",
    )
    await _log(
        bot,
        thread.guild,
        category="community",
        event="thread.create",
        action="Thread created",
        target=_entity_label(thread),
        details=[f"**Parent channel:** {_entity_label(thread.parent)}"],
        severity="moderate",
        executor=entry.user if entry else None,
        reason=entry.reason if entry else None,
        timestamp=entry.created_at if entry else None,
    )


async def on_thread_delete(bot: commands.Bot, thread: discord.Thread) -> None:
    entry = await _find_audit_entry(
        bot,
        thread.guild,
        "thread_delete",
        thread.id,
        category="community",
        event="thread.delete",
    )
    await _log(
        bot,
        thread.guild,
        category="community",
        event="thread.delete",
        action="Thread deleted",
        target=_entity_label(thread),
        details=[f"**Parent channel:** {_entity_label(thread.parent)}"],
        severity="major",
        executor=entry.user if entry else None,
        reason=entry.reason if entry else None,
        timestamp=entry.created_at if entry else None,
    )


async def on_thread_update(
    bot: commands.Bot,
    before: discord.Thread,
    after: discord.Thread,
) -> None:
    changes = _change_lines(
        before,
        after,
        (
            ("name", "Name"),
            ("archived", "Archived"),
            ("locked", "Locked"),
            ("invitable", "Invitable"),
            ("auto_archive_duration", "Auto-archive duration"),
            ("slowmode_delay", "Slowmode"),
        ),
    )
    if changes:
        entry = await _find_audit_entry(
            bot,
            after.guild,
            "thread_update",
            after.id,
            category="community",
            event="thread.update",
        )
        await _log(
            bot,
            after.guild,
            category="community",
            event="thread.update",
            action="Thread settings changed",
            target=_entity_label(after),
            details=changes,
            severity="moderate",
            executor=entry.user if entry else None,
            reason=entry.reason if entry else None,
            timestamp=entry.created_at if entry else None,
        )


async def on_scheduled_event_create(
    bot: commands.Bot,
    event: discord.ScheduledEvent,
) -> None:
    await _log(
        bot,
        event.guild,
        category="community",
        event="scheduled_event.create",
        action="Scheduled event created",
        target=_entity_label(event),
        details=[
            f"**Starts:** {_display(event.start_time)}",
            f"**Location:** {_display(event.location or event.channel)}",
        ],
        severity="moderate",
        executor=event.creator,
    )


async def on_scheduled_event_delete(
    bot: commands.Bot,
    event: discord.ScheduledEvent,
) -> None:
    await _log(
        bot,
        event.guild,
        category="community",
        event="scheduled_event.delete",
        action="Scheduled event deleted",
        target=_entity_label(event),
        severity="major",
    )


async def on_scheduled_event_update(
    bot: commands.Bot,
    before: discord.ScheduledEvent,
    after: discord.ScheduledEvent,
) -> None:
    changes = _change_lines(
        before,
        after,
        (
            ("name", "Name"),
            ("description", "Description"),
            ("start_time", "Start time"),
            ("end_time", "End time"),
            ("status", "Status"),
            ("location", "Location"),
            ("privacy_level", "Privacy"),
        ),
    )
    if changes:
        await _log(
            bot,
            after.guild,
            category="community",
            event="scheduled_event.update",
            action="Scheduled event updated",
            target=_entity_label(after),
            details=changes,
            severity="moderate",
        )


async def _automod_rule_event(
    bot: commands.Bot,
    rule: discord.AutoModRule,
    *,
    action: str,
    event: str,
    severity: str,
) -> None:
    await _log(
        bot,
        rule.guild,
        category="community",
        event=event,
        action=action,
        target=_entity_label(rule),
        details=[f"**Trigger:** `{rule.trigger.type}`"],
        severity=severity,
    )


async def on_automod_rule_create(bot: commands.Bot, rule: discord.AutoModRule) -> None:
    await _automod_rule_event(
        bot,
        rule,
        action="AutoMod rule created",
        event="automod.rule_create",
        severity="major",
    )


async def on_automod_rule_update(
    bot: commands.Bot,
    rule: discord.AutoModRule,
) -> None:
    await _automod_rule_event(
        bot,
        rule,
        action="AutoMod rule updated",
        event="automod.rule_update",
        severity="moderate",
    )


async def on_automod_rule_delete(
    bot: commands.Bot,
    rule: discord.AutoModRule,
) -> None:
    await _automod_rule_event(
        bot,
        rule,
        action="AutoMod rule deleted",
        event="automod.rule_delete",
        severity="major",
    )


async def on_automod_action(
    bot: commands.Bot,
    execution: discord.AutoModAction,
) -> None:
    guild = bot.get_guild(execution.guild_id)
    if guild is None:
        return
    await _log(
        bot,
        guild,
        category="community",
        event="automod.action",
        action="AutoMod action executed",
        target=f"User `{execution.user_id}`",
        details=[
            f"**Action:** `{execution.action.type}`",
            f"**Rule:** `{execution.rule_id}`",
            f"**Channel:** <#{execution.channel_id}>",
            f"**Matched content:** `{_display(execution.matched_content)}`",
        ],
        severity="moderate",
    )


listeners: dict[str, Any] = {
    "on_user_update": on_user_update,
    "on_member_update": on_member_update,
    "on_member_join": on_member_join,
    "on_message_edit": on_message_edit,
    "on_raw_message_edit": on_raw_message_edit,
    "on_raw_message_delete": on_raw_message_delete,
    "on_raw_bulk_message_delete": on_raw_bulk_message_delete,
    "on_guild_channel_pins_update": on_guild_channel_pins_update,
    "on_member_ban": on_member_ban,
    "on_member_unban": on_member_unban,
    "on_member_remove": on_member_remove,
    "on_voice_state_update": on_voice_state_update,
    "on_guild_update": on_guild_update,
    "on_guild_role_create": on_guild_role_create,
    "on_guild_role_delete": on_guild_role_delete,
    "on_guild_role_update": on_guild_role_update,
    "on_guild_channel_create": on_guild_channel_create,
    "on_guild_channel_delete": on_guild_channel_delete,
    "on_guild_channel_update": on_guild_channel_update,
    "on_webhooks_update": on_webhooks_update,
    "on_invite_create": on_invite_create,
    "on_invite_delete": on_invite_delete,
    "on_guild_emojis_update": on_guild_emojis_update,
    "on_guild_stickers_update": on_guild_stickers_update,
    "on_guild_integrations_update": on_guild_integrations_update,
    "on_thread_create": on_thread_create,
    "on_thread_delete": on_thread_delete,
    "on_thread_update": on_thread_update,
    "on_scheduled_event_create": on_scheduled_event_create,
    "on_scheduled_event_delete": on_scheduled_event_delete,
    "on_scheduled_event_update": on_scheduled_event_update,
    "on_automod_rule_create": on_automod_rule_create,
    "on_automod_rule_update": on_automod_rule_update,
    "on_automod_rule_delete": on_automod_rule_delete,
    "on_automod_action": on_automod_action,
}

__all__ = ("listeners",)
