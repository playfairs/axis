from __future__ import annotations

import asyncio
import re
import time
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta

from discord import app_commands

from bot.base.imports import commands, discord, logger

MAX_KEYWORDS = 1000
MAX_ALLOW_LIST = 100
MAX_REGEX_PATTERNS = 10
MAX_KEYWORD_LENGTH = 60
MAX_REGEX_LENGTH = 260
MAX_EXEMPT_ROLES = 20
MAX_EXEMPT_CHANNELS = 50
MAX_TIMEOUT = timedelta(days=28)
PAGE_SIZE = 8
RULE_CACHE_TTL = 60.0
SCP_NAME = re.compile(r"^\[SCP:(strict|balanced|aggressive):(cs|ci):(o[01])\]\s*")
ROLE_ID = re.compile(r"<@&(\d+)>")
CHANNEL_ID = re.compile(r"<#(\d+)>")
CONFUSABLES = str.maketrans(
    {
        "а": "a",
        "в": "b",
        "с": "c",
        "е": "e",
        "һ": "h",
        "і": "i",
        "ј": "j",
        "к": "k",
        "м": "m",
        "н": "h",
        "о": "o",
        "р": "p",
        "ѕ": "s",
        "т": "t",
        "х": "x",
        "у": "y",
        "А": "A",
        "В": "B",
        "С": "C",
        "Е": "E",
        "Н": "H",
        "І": "I",
        "Ј": "J",
        "К": "K",
        "М": "M",
        "О": "O",
        "Р": "P",
        "Ѕ": "S",
        "Т": "T",
        "Х": "X",
        "У": "Y",
        "Α": "A",
        "α": "a",
        "Β": "B",
        "β": "b",
        "Ε": "E",
        "ε": "e",
        "Ι": "I",
        "ι": "i",
        "Κ": "K",
        "κ": "k",
        "Μ": "M",
        "μ": "m",
        "Ν": "N",
        "ν": "v",
        "Ο": "O",
        "ο": "o",
        "Ρ": "P",
        "ρ": "p",
        "Τ": "T",
        "τ": "t",
        "Χ": "X",
        "χ": "x",
    }
)

TRIGGER_TYPES: dict[str, discord.AutoModRuleTriggerType] = {
    "keyword": discord.AutoModRuleTriggerType.keyword,
    "spam": discord.AutoModRuleTriggerType.spam,
    "keyword_preset": discord.AutoModRuleTriggerType.keyword_preset,
    "mention_spam": discord.AutoModRuleTriggerType.mention_spam,
    "member_profile": discord.AutoModRuleTriggerType.member_profile,
    "harmful_link": discord.AutoModRuleTriggerType.harmful_link,
}
PRESET_FLAGS = {
    "profanity": "profanity",
    "sexual_content": "sexual_content",
    "slurs": "slurs",
}
TRIGGER_CHOICES = [
    app_commands.Choice(name=value.replace("_", " ").title(), value=value)
    for value in TRIGGER_TYPES
]
FILTER_CHOICES = [
    app_commands.Choice(name="Keywords", value="keyword"),
    app_commands.Choice(name="Regex patterns", value="regex"),
]
MODE_CHOICES = [
    app_commands.Choice(name=value.title(), value=value)
    for value in ("strict", "balanced", "aggressive")
]


@dataclass(slots=True)
class RuleSpec:
    name: str
    event_type: discord.AutoModRuleEventType
    trigger: discord.AutoModTrigger
    actions: list[discord.AutoModRuleAction]
    enabled: bool
    exempt_roles: list[discord.Role]
    exempt_channels: list[discord.abc.GuildChannel]


def _csv_values(value: str | None) -> list[str]:
    if value is None:
        return []
    values = [
        item.strip()
        for item in re.split(r"[,;\n]", value)
        if item.strip()
    ]
    return list(dict.fromkeys(values))


def _regex_values(value: str | None) -> list[str]:
    if value is None:
        return []
    return list(
        dict.fromkeys(
            item.strip()
            for item in re.split(r"[;\n]", value)
            if item.strip()
        )
    )


def _validate_filters(
    keywords: Sequence[str],
    regex_patterns: Sequence[str],
    allow_list: Sequence[str],
    *,
    trigger_type: discord.AutoModRuleTriggerType,
) -> None:
    if len(keywords) > MAX_KEYWORDS:
        raise ValueError(f"A rule can contain at most {MAX_KEYWORDS} keywords.")
    if len(regex_patterns) > MAX_REGEX_PATTERNS:
        raise ValueError(
            f"A rule can contain at most {MAX_REGEX_PATTERNS} regex patterns."
        )
    allow_limit = 1000 if trigger_type is discord.AutoModRuleTriggerType.keyword_preset else MAX_ALLOW_LIST
    if len(allow_list) > allow_limit:
        raise ValueError(f"This rule type allows at most {allow_limit} exceptions.")
    if any(len(value) > MAX_KEYWORD_LENGTH for value in (*keywords, *allow_list)):
        raise ValueError(
            f"Keywords and exceptions must be {MAX_KEYWORD_LENGTH} characters or fewer."
        )
    if any(len(pattern) > MAX_REGEX_LENGTH for pattern in regex_patterns):
        raise ValueError(
            f"Regex patterns must be {MAX_REGEX_LENGTH} characters or fewer."
        )


def _build_trigger(
    trigger_name: str,
    *,
    keywords: str | None = None,
    regex_patterns: str | None = None,
    presets: str | None = None,
    allow_list: str | None = None,
    mention_limit: int | None = None,
    mention_raid_protection: bool = False,
) -> tuple[discord.AutoModRuleEventType, discord.AutoModTrigger]:
    normalized_type = trigger_name.casefold()
    trigger_type = TRIGGER_TYPES.get(normalized_type)
    if trigger_type is None:
        raise ValueError(
            "Choose keyword, spam, keyword_preset, mention_spam, "
            "member_profile, or harmful_link."
        )

    keyword_values = _csv_values(keywords)
    pattern_values = _regex_values(regex_patterns)
    allow_values = _csv_values(allow_list)
    preset_values = _csv_values(presets)
    if trigger_type in (
        discord.AutoModRuleTriggerType.keyword,
        discord.AutoModRuleTriggerType.member_profile,
    ):
        if presets is not None and preset_values:
            raise ValueError("Keyword presets require a keyword_preset rule.")
        _validate_filters(
            keyword_values,
            pattern_values,
            allow_values,
            trigger_type=trigger_type,
        )
        trigger = discord.AutoModTrigger(
            type=trigger_type,
            keyword_filter=keyword_values,
            regex_patterns=pattern_values,
            allow_list=allow_values,
        )
    elif trigger_type is discord.AutoModRuleTriggerType.keyword_preset:
        if keyword_values or pattern_values:
            raise ValueError(
                "Keyword preset rules use `presets`, not keywords or regex."
            )
        invalid = [value for value in preset_values if value.casefold() not in PRESET_FLAGS]
        if invalid:
            raise ValueError(
                "Unknown presets: "
                + ", ".join(invalid)
                + ". Use profanity, sexual_content, or slurs."
            )
        if not preset_values:
            raise ValueError("Choose at least one keyword preset.")
        _validate_filters([], [], allow_values, trigger_type=trigger_type)
        flags = {PRESET_FLAGS[value.casefold()]: True for value in preset_values}
        trigger = discord.AutoModTrigger(
            type=trigger_type,
            presets=discord.AutoModPresets(**flags),
            allow_list=allow_values,
        )
    elif trigger_type is discord.AutoModRuleTriggerType.mention_spam:
        if keyword_values or pattern_values or preset_values or allow_values:
            raise ValueError("Mention spam rules do not accept keyword filters.")
        count = 5 if mention_limit is None else mention_limit
        if not 1 <= count <= 50:
            raise ValueError("Mention limit must be between 1 and 50.")
        trigger = discord.AutoModTrigger(
            type=trigger_type,
            mention_limit=count,
            mention_raid_protection=mention_raid_protection,
        )
    else:
        if keyword_values or pattern_values or preset_values or allow_values:
            raise ValueError(
                "Spam and harmful-link rules do not accept custom filters."
            )
        trigger = discord.AutoModTrigger(type=trigger_type)

    event_type = (
        discord.AutoModRuleEventType.member_update
        if trigger_type is discord.AutoModRuleTriggerType.member_profile
        else discord.AutoModRuleEventType.message_send
    )
    return event_type, trigger


def _parse_timeout(value: str) -> timedelta:
    match = re.fullmatch(r"\s*(\d+)\s*(s|m|h|d|w)?\s*", value, re.IGNORECASE)
    if match is None:
        raise ValueError("Use a timeout such as `600`, `10m`, `2h`, or `1d`.")
    amount = int(match.group(1))
    unit_seconds = {
        None: 1,
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }[match.group(2).casefold() if match.group(2) else None]
    duration = timedelta(seconds=amount * unit_seconds)
    if duration <= timedelta(0) or duration > MAX_TIMEOUT:
        raise ValueError("AutoMod timeouts must be from 1 second to 28 days.")
    return duration


def _build_actions(
    action_spec: str | None,
    *,
    guild: discord.Guild,
    actor: discord.Member,
    trigger_type: discord.AutoModRuleTriggerType,
    alert_channel: discord.TextChannel | None,
    custom_message: str | None,
) -> list[discord.AutoModRuleAction]:
    parts = _csv_values(action_spec or "block")
    if not parts:
        raise ValueError("Configure at least one AutoMod action.")
    actions: list[discord.AutoModRuleAction] = []
    action_types: set[discord.AutoModRuleActionType] = set()
    for part in parts:
        lowered = part.casefold()
        if lowered == "block":
            action = discord.AutoModRuleAction(
                type=discord.AutoModRuleActionType.block_message,
                custom_message=custom_message,
            )
        elif lowered == "alert":
            if alert_channel is None or alert_channel.guild != guild:
                raise ValueError(
                    "Choose an alert channel when using the `alert` action."
                )
            action = discord.AutoModRuleAction(channel_id=alert_channel.id)
        elif lowered.startswith(("timeout=", "timeout:")):
            if trigger_type not in (
                discord.AutoModRuleTriggerType.keyword,
                discord.AutoModRuleTriggerType.mention_spam,
            ):
                raise ValueError(
                    "Discord only supports AutoMod timeouts for keyword and "
                    "mention_spam rules."
                )
            duration = _parse_timeout(part[len("timeout=") :] if "=" in part else part[len("timeout:") :])
            bot_member = guild.me
            if not actor.guild_permissions.moderate_members:
                raise ValueError("You need Moderate Members to configure timeouts.")
            if bot_member is None or not bot_member.guild_permissions.moderate_members:
                raise ValueError("I need Moderate Members to apply AutoMod timeouts.")
            action = discord.AutoModRuleAction(duration=duration)
        elif lowered in {"interactions", "block_interactions"}:
            action = discord.AutoModRuleAction(
                type=discord.AutoModRuleActionType.block_member_interactions
            )
        else:
            raise ValueError(
                "Actions must be comma-separated `block`, `alert`, "
                "`timeout=10m`, or `interactions`."
            )
        if action.type in action_types:
            raise ValueError(f"The `{lowered}` action was specified more than once.")
        action_types.add(action.type)
        actions.append(action)

    if alert_channel is not None and not any(
        action.type is discord.AutoModRuleActionType.send_alert_message
        for action in actions
    ):
        raise ValueError("An alert channel is only used with the `alert` action.")
    if custom_message is not None and not any(
        action.type is discord.AutoModRuleActionType.block_message
        for action in actions
    ):
        raise ValueError("Custom messages require the `block` action.")
    if custom_message is not None and len(custom_message) > 150:
        raise ValueError("Custom block messages must be 150 characters or fewer.")
    return actions


def _parse_entities(
    raw: str | None,
    *,
    guild: discord.Guild,
    roles: bool,
) -> list[discord.Role] | list[discord.abc.GuildChannel]:
    if raw is None or not raw.strip():
        return []
    if raw.strip().casefold() in {"clear", "none"}:
        return []
    values = [value.strip() for value in re.split(r"[,;\n]", raw) if value.strip()]
    result: list[discord.Role] | list[discord.abc.GuildChannel] = []
    for value in values:
        mention = (ROLE_ID if roles else CHANNEL_ID).fullmatch(value)
        id_text = mention.group(1) if mention is not None else value
        if not id_text.isdecimal():
            raise ValueError("Use comma-separated role/channel mentions or IDs.")
        entity_id = int(id_text)
        entity = guild.get_role(entity_id) if roles else guild.get_channel(entity_id)
        if entity is None:
            raise ValueError(f"Couldn't find `{entity_id}` in this server.")
        if roles:
            if not isinstance(entity, discord.Role):
                raise ValueError(f"`{entity_id}` is not a role in this server.")
        elif not isinstance(entity, discord.abc.GuildChannel):
            raise ValueError(f"`{entity_id}` is not a channel in this server.")
        result.append(entity)
    limit = MAX_EXEMPT_ROLES if roles else MAX_EXEMPT_CHANNELS
    if len(result) > limit:
        raise ValueError(f"You can exempt at most {limit} {'roles' if roles else 'channels'}.")
    return result


def _build_spec(
    *,
    guild: discord.Guild,
    actor: discord.Member,
    name: str,
    trigger_name: str,
    actions: str | None,
    alert_channel: discord.TextChannel | None,
    keywords: str | None,
    regex_patterns: str | None,
    presets: str | None,
    allow_list: str | None,
    exempt_roles: str | None,
    exempt_channels: str | None,
    enabled: bool,
    custom_message: str | None,
    mention_limit: int | None = None,
    mention_raid_protection: bool = False,
) -> RuleSpec:
    name = name.strip()
    if not name or len(name) > 100:
        raise ValueError("Rule names must be between 1 and 100 characters.")
    event_type, trigger = _build_trigger(
        trigger_name,
        keywords=keywords,
        regex_patterns=regex_patterns,
        presets=presets,
        allow_list=allow_list,
        mention_limit=mention_limit,
        mention_raid_protection=mention_raid_protection,
    )
    actions_value = _build_actions(
        actions,
        guild=guild,
        actor=actor,
        trigger_type=trigger.type,
        alert_channel=alert_channel,
        custom_message=custom_message,
    )
    exempt_role_values = _parse_entities(exempt_roles, guild=guild, roles=True)
    exempt_channel_values = _parse_entities(
        exempt_channels,
        guild=guild,
        roles=False,
    )
    return RuleSpec(
        name=name,
        event_type=event_type,
        trigger=trigger,
        actions=actions_value,
        enabled=enabled,
        exempt_roles=exempt_role_values,
        exempt_channels=exempt_channel_values,
    )


async def _send(
    ctx: commands.Context,
    content: str | None = None,
    *,
    embed: discord.Embed | None = None,
    view: discord.ui.View | None = None,
) -> discord.Message:
    return await ctx.send(
        content,
        embed=embed,
        view=view,
        ephemeral=ctx.interaction is not None,
        allowed_mentions=discord.AllowedMentions.none(),
    )


async def _send_error(ctx: commands.Context, message: str) -> None:
    await _send(ctx, message)


async def _get_guild(ctx: commands.Context) -> discord.Guild | None:
    if ctx.guild is None:
        await _send_error(ctx, "AutoMod commands can only be used in a server.")
        return None
    return ctx.guild


async def _fetch_rules(ctx: commands.Context) -> list[discord.AutoModRule] | None:
    guild = await _get_guild(ctx)
    if guild is None:
        return None
    try:
        return await guild.fetch_automod_rules()
    except discord.Forbidden:
        await _send_error(ctx, "I need Manage Server to retrieve AutoMod rules.")
    except discord.HTTPException as error:
        logger.warning(
            "Could not fetch AutoMod rules for guild %s (HTTP %s).",
            guild.id,
            error.status,
        )
        await _send_error(ctx, "Discord couldn't retrieve the AutoMod rules.")
    return None


async def _fetch_rule(
    ctx: commands.Context,
    rule_id: str,
) -> discord.AutoModRule | None:
    if not rule_id.isdecimal() or int(rule_id) <= 0:
        await _send_error(ctx, "Enter a valid Discord AutoMod rule ID.")
        return None
    rules = await _fetch_rules(ctx)
    if rules is None:
        return None
    rule = next((item for item in rules if item.id == int(rule_id)), None)
    if rule is None:
        await _send_error(ctx, f"No AutoMod rule with ID `{rule_id}` exists here.")
    return rule


async def _create_rule(
    guild: discord.Guild,
    spec: RuleSpec,
    *,
    reason: str,
) -> discord.AutoModRule:
    return await guild.create_automod_rule(
        name=spec.name,
        event_type=spec.event_type,
        trigger=spec.trigger,
        actions=spec.actions,
        enabled=spec.enabled,
        exempt_roles=spec.exempt_roles,
        exempt_channels=spec.exempt_channels,
        reason=reason,
    )


async def _report_api_error(
    ctx: commands.Context,
    error: discord.HTTPException,
    operation: str,
) -> None:
    logger.warning(
        "AutoMod %s failed in guild %s (HTTP %s).",
        operation,
        ctx.guild.id if ctx.guild else "unknown",
        error.status,
    )
    if isinstance(error, discord.Forbidden):
        await _send_error(ctx, "I don't have permission to manage AutoMod rules.")
    else:
        await _send_error(
            ctx,
            "Discord couldn't complete that AutoMod operation. Check the rule "
            "settings, permissions, and API limits.",
        )


def _format_action(action: discord.AutoModRuleAction) -> str:
    name = action.type.name.replace("_", " ").title()
    if action.channel_id is not None:
        return f"{name} in <#{action.channel_id}>"
    if action.duration is not None:
        return f"{name} for {action.duration}"
    if action.custom_message:
        return f"{name}: {action.custom_message}"
    return name


def _display_values(values: Sequence[str], limit: int = 900) -> str:
    if not values:
        return "None"
    output = ", ".join(f"`{value}`" for value in values)
    if len(output) <= limit:
        return output
    clipped = output[: limit - 32].rsplit(", ", 1)[0]
    return f"{clipped}, … ({len(values)} total)"


def _rule_embed(rule: discord.AutoModRule) -> discord.Embed:
    trigger = rule.trigger
    embed = discord.Embed(
        title=discord.utils.escape_markdown(rule.name),
        description=(
            f"Rule ID: `{rule.id}`\n"
            f"Type: `{trigger.type.name.replace('_', ' ').title()}`\n"
            f"Event: `{rule.event_type.name.replace('_', ' ').title()}`\n"
            f"Status: **{'Enabled' if rule.enabled else 'Disabled'}**"
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Actions",
        value="\n".join(_format_action(action) for action in rule.actions) or "None",
        inline=False,
    )
    embed.add_field(
        name=f"Keywords ({len(trigger.keyword_filter)})",
        value=_display_values(trigger.keyword_filter),
        inline=False,
    )
    embed.add_field(
        name=f"Regex patterns ({len(trigger.regex_patterns)})",
        value=_display_values(trigger.regex_patterns),
        inline=False,
    )
    embed.add_field(
        name=f"Allow-list ({len(trigger.allow_list)})",
        value=_display_values(trigger.allow_list),
        inline=False,
    )
    if trigger.type is discord.AutoModRuleTriggerType.keyword_preset:
        embed.add_field(
            name="Keyword presets",
            value=", ".join(
                name
                for name in PRESET_FLAGS
                if getattr(trigger.presets, name)
            )
            or "None",
            inline=False,
        )
    if trigger.type is discord.AutoModRuleTriggerType.mention_spam:
        embed.add_field(
            name="Mention limit",
            value=str(trigger.mention_limit),
            inline=True,
        )
        embed.add_field(
            name="Mention raid protection",
            value=str(trigger.mention_raid_protection),
            inline=True,
        )
    role_ids = list(rule.exempt_role_ids)
    channel_ids = list(rule.exempt_channel_ids)
    embed.add_field(
        name=f"Exempt roles ({len(role_ids)})",
        value=", ".join(f"<@&{role_id}>" for role_id in role_ids) or "None",
        inline=False,
    )
    embed.add_field(
        name=f"Exempt channels ({len(channel_ids)})",
        value=", ".join(f"<#{channel_id}>" for channel_id in channel_ids) or "None",
        inline=False,
    )
    scp = _parse_scp_name(rule.name)
    if scp is not None:
        embed.add_field(
            name="SCP preview",
            value=(
                f"Mode: {scp[0]} · Case-sensitive: {scp[1]} · "
                f"Obfuscation detection: {scp[2]}\n"
                "Unicode normalization and confusable matching are supplemented "
                "by the bot; this is not a native Discord AutoMod capability."
            ),
            inline=False,
        )
    return embed


class _EmbedPages(discord.ui.View):
    def __init__(
        self,
        owner_id: int,
        pages: Sequence[discord.Embed],
    ) -> None:
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.pages = list(pages)
        self.index = 0
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.previous.disabled = self.index == 0
        self.next.disabled = self.index >= len(self.pages) - 1
        if hasattr(self, "rule_select"):
            self.rule_select.options = self._rule_options()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message(
            "Only the person who opened this page can use these controls.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        self.index -= 1
        self._update_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.index],
            view=self,
        )

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        self.index += 1
        self._update_buttons()
        await interaction.response.edit_message(
            embed=self.pages[self.index],
            view=self,
        )


class _RulePages(_EmbedPages):
    def __init__(
        self,
        owner_id: int,
        rules: Sequence[discord.AutoModRule],
    ) -> None:
        self.rules = list(rules)
        super().__init__(
            owner_id,
            _make_text_pages(
                f"AutoMod rules ({len(rules)})",
                [_rule_summary(rule) for rule in rules],
            ),
        )
        self.rule_select = discord.ui.Select(
            placeholder="Select a rule to inspect",
            options=self._rule_options(),
            min_values=1,
            max_values=1,
            row=1,
        )
        self.rule_select.callback = self._show_selected_rule
        self.add_item(self.rule_select)

    def _rule_options(self) -> list[discord.SelectOption]:
        rules = self.rules[self.index * PAGE_SIZE : (self.index + 1) * PAGE_SIZE]
        return [
            discord.SelectOption(
                label=rule.name[:100],
                value=str(rule.id),
                description=(
                    f"{rule.trigger.type.name.replace('_', ' ')} · "
                    f"{'enabled' if rule.enabled else 'disabled'} · {rule.id}"
                )[:100],
            )
            for rule in rules
        ]

    async def _show_selected_rule(
        self,
        interaction: discord.Interaction,
    ) -> None:
        rule_id = int(self.rule_select.values[0])
        rule = next((item for item in self.rules if item.id == rule_id), None)
        if rule is None:
            await interaction.response.send_message(
                "That rule is no longer in this list. Run `automod rules` again.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message(
            embed=_rule_embed(rule),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


def _make_text_pages(title: str, values: Sequence[str]) -> list[discord.Embed]:
    pages = []
    for page_index in range(0, max(1, len(values)), PAGE_SIZE):
        page_values = values[page_index : page_index + PAGE_SIZE]
        body = "\n".join(page_values) if page_values else "No entries."
        embed = discord.Embed(
            title=title,
            description=body[:4000],
            color=discord.Color.blurple(),
        )
        total_pages = max(1, (len(values) + PAGE_SIZE - 1) // PAGE_SIZE)
        embed.set_footer(
            text=f"Page {page_index // PAGE_SIZE + 1}/{total_pages}"
        )
        pages.append(embed)
    return pages


async def _show_pages(
    ctx: commands.Context,
    pages: Sequence[discord.Embed],
) -> None:
    view = _EmbedPages(ctx.author.id, pages)
    await _send(ctx, embed=pages[0], view=view)


def _rule_summary(rule: discord.AutoModRule) -> str:
    trigger = rule.trigger
    action_text = ", ".join(_format_action(action) for action in rule.actions)
    return (
        f"**{discord.utils.escape_markdown(rule.name)}** (`{rule.id}`) — "
        f"{trigger.type.name.replace('_', ' ').title()}, "
        f"{'enabled' if rule.enabled else 'disabled'}\n"
        f"Actions: {action_text or 'None'} · "
        f"Keywords: {len(trigger.keyword_filter)} · "
        f"Regex: {len(trigger.regex_patterns)} · "
        f"Exempt roles/channels: {len(rule.exempt_role_ids)}/"
        f"{len(rule.exempt_channel_ids)}"
    )


async def _list_rules(
    ctx: commands.Context,
    rule_id: str | None = None,
) -> None:
    if rule_id is not None:
        rule = await _fetch_rule(ctx, rule_id)
        if rule is not None:
            await _send(ctx, embed=_rule_embed(rule))
        return
    rules = await _fetch_rules(ctx)
    if rules is None:
        return
    if not rules:
        await _send(ctx, "This server has no AutoMod rules.")
        return
    view = _RulePages(ctx.author.id, rules)
    await _send(ctx, embed=view.pages[0], view=view)


def _clone_trigger(
    trigger: discord.AutoModTrigger,
    *,
    keyword_filter: Sequence[str] | None = None,
    regex_patterns: Sequence[str] | None = None,
    allow_list: Sequence[str] | None = None,
) -> discord.AutoModTrigger:
    return discord.AutoModTrigger(
        type=trigger.type,
        keyword_filter=list(
            trigger.keyword_filter if keyword_filter is None else keyword_filter
        ),
        regex_patterns=list(
            trigger.regex_patterns if regex_patterns is None else regex_patterns
        ),
        allow_list=list(trigger.allow_list if allow_list is None else allow_list),
        presets=trigger.presets,
        mention_limit=trigger.mention_limit,
        mention_raid_protection=trigger.mention_raid_protection,
    )


def _copy_values_for_matching(
    existing: Sequence[str],
    values: Sequence[str],
    *,
    add: bool,
) -> tuple[list[str], list[str], list[str]]:
    normalized = {value.casefold() for value in existing}
    if add:
        duplicates = [value for value in values if value.casefold() in normalized]
        result = list(existing)
        for value in values:
            folded = value.casefold()
            if folded not in normalized:
                result.append(value)
                normalized.add(folded)
        return result, [], duplicates
    remove_set = {value.casefold() for value in values}
    result = [value for value in existing if value.casefold() not in remove_set]
    removed = [value for value in existing if value.casefold() in remove_set]
    missing = [value for value in values if value.casefold() not in normalized]
    return result, removed, missing


def _parse_scp_name(name: str) -> tuple[str, bool, bool] | None:
    match = SCP_NAME.match(name)
    if match is None:
        return None
    return (
        match.group(1),
        match.group(2) == "cs",
        match.group(3) == "o1",
    )


def _normalise_scp_text(
    text: str,
    *,
    mode: str,
    case_sensitive: bool,
    detect_obfuscation: bool,
) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    if detect_obfuscation:
        normalized = normalized.translate(CONFUSABLES)
    if detect_obfuscation and mode == "aggressive":
        normalized = re.sub(r"(.)\1{2,}", r"\1\1", normalized)
    return normalized if case_sensitive else normalized.casefold()


def _exception_matches(text: str, exceptions: Sequence[str], *, case_sensitive: bool) -> str | None:
    text_tokens = re.findall(r"\w+", text, flags=re.UNICODE)
    if not case_sensitive:
        text_tokens = [token.casefold() for token in text_tokens]
    for exception in exceptions:
        tokens = re.findall(r"\w+", exception, flags=re.UNICODE)
        if not case_sensitive:
            tokens = [token.casefold() for token in tokens]
        if tokens and any(
            text_tokens[index : index + len(tokens)] == tokens
            for index in range(len(text_tokens) - len(tokens) + 1)
        ):
            return exception
    return None


def _keyword_match(text: str, keyword: str, *, case_sensitive: bool) -> bool:
    escaped = re.escape(keyword)
    start_wildcard = keyword.startswith("*")
    end_wildcard = keyword.endswith("*")
    literal = keyword.strip("*")
    if not literal:
        return False
    escaped = re.escape(literal)
    if not start_wildcard:
        escaped = rf"\b{escaped}"
    if not end_wildcard:
        escaped = rf"{escaped}\b"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.search(escaped, text, flags=flags) is not None


def _evaluate_scp(
    rule: discord.AutoModRule,
    text: str,
) -> tuple[str | None, str | None, str | None]:
    metadata = _parse_scp_name(rule.name) or ("balanced", False, True)
    mode, case_sensitive, detect_obfuscation = metadata
    normalized = _normalise_scp_text(
        text,
        mode=mode,
        case_sensitive=case_sensitive,
        detect_obfuscation=detect_obfuscation,
    )
    exception = _exception_matches(
        normalized,
        rule.trigger.allow_list,
        case_sensitive=case_sensitive,
    )
    if exception is not None:
        return None, exception, None
    for keyword in rule.trigger.keyword_filter:
        if _keyword_match(
            normalized,
            keyword,
            case_sensitive=case_sensitive,
        ):
            match_type = "substring/wildcard" if "*" in keyword else "exact keyword"
            return keyword, None, match_type
    for pattern in rule.trigger.regex_patterns:
        try:
            match = re.search(pattern, normalized)
        except re.error:
            continue
        if match is not None:
            match_type = (
                "obfuscated regex"
                if "[" in pattern or r"\s" in pattern
                else "exact regex"
            )
            return match.group(0) or pattern, None, match_type
    return None, None, None


def _scp_pattern(
    term: str,
    *,
    mode: str,
    case_sensitive: bool,
    word_boundaries: bool,
    detect_obfuscation: bool,
    detect_separators: bool,
) -> str:
    substitution_sets = {
        "balanced": {"a": "a4@", "e": "e3", "i": "i1!", "o": "o0", "s": "s5$", "t": "t7"},
        "aggressive": {
            "a": "a4@",
            "b": "b8",
            "e": "e3",
            "g": "g9",
            "i": "i1!|",
            "l": "l1|",
            "o": "o0",
            "s": "s5$",
            "t": "t7",
            "z": "z2",
        },
    }
    substitutions = substitution_sets.get(mode, {}) if detect_obfuscation else {}
    pieces: list[str] = []
    for index, character in enumerate(term):
        if character.isspace():
            pieces.append(r"\s+")
            continue
        alternatives = substitutions.get(character.casefold())
        if alternatives is not None:
            if case_sensitive and character.isupper():
                alternatives = alternatives.replace(
                    character.casefold(),
                    character,
                )
            escaped = "".join(re.escape(value) for value in alternatives)
            pieces.append(f"[{escaped}]")
        else:
            pieces.append(re.escape(character))
        if (
            detect_separators
            and index + 1 < len(term)
            and not term[index + 1].isspace()
        ):
            pieces.append(r"[\s._-]{0,2}")
    pattern = "".join(pieces)
    if word_boundaries:
        pattern = rf"\b{pattern}\b"
    if not case_sensitive:
        pattern = f"(?i){pattern}"
    if len(pattern) > MAX_REGEX_LENGTH:
        raise ValueError(
            f"The generated regex for `{term}` exceeds {MAX_REGEX_LENGTH} "
            "characters; shorten the term or disable obfuscation/separator detection."
        )
    return pattern


async def _create_spec_for_context(
    ctx: commands.Context,
    spec: RuleSpec,
    *,
    operation: str = "create",
) -> discord.AutoModRule | None:
    guild = ctx.guild
    if guild is None:
        await _send_error(ctx, "AutoMod commands can only be used in a server.")
        return None
    try:
        rule = await _create_rule(
            guild,
            spec,
            reason=f"{operation} by {ctx.author} via AutoMod command",
        )
    except discord.Forbidden as error:
        await _report_api_error(ctx, error, operation)
        return None
    except discord.HTTPException as error:
        await _report_api_error(ctx, error, operation)
        return None
    await _send(
        ctx,
        f"Created AutoMod rule **{discord.utils.escape_markdown(rule.name)}** "
        f"with ID `{rule.id}` ({'enabled' if rule.enabled else 'disabled'}).",
    )
    return rule


@commands.hybrid_group(
    name="automod",
    description="Manage native Discord AutoMod rules.",
    invoke_without_command=True,
)
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
@commands.bot_has_guild_permissions(manage_guild=True)
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
@app_commands.checks.has_permissions(manage_guild=True)
async def automod(ctx: commands.Context) -> None:
    await _list_rules(ctx)


@automod.command(name="create", description="Create a native Discord AutoMod rule.")
@app_commands.choices(trigger_type=TRIGGER_CHOICES)
@app_commands.describe(
    trigger_type="Native Discord AutoMod trigger type.",
    actions="Comma-separated: block, alert, timeout=10m, interactions.",
    keywords="Comma/newline-separated; empty keyword rules are allowed.",
    regex_patterns="Rust-regex patterns separated by newlines or semicolons.",
    presets="For keyword_preset: profanity, sexual_content, and/or slurs.",
    allow_list="Comma/newline-separated exceptions.",
    alert_channel="Required when actions include alert.",
    exempt_roles="Comma-separated role mentions or IDs.",
    exempt_channels="Comma-separated channel mentions or IDs.",
)
async def automod_create(
    ctx: commands.Context,
    name: str,
    trigger_type: str,
    actions: str = "block",
    alert_channel: discord.TextChannel | None = None,
    keywords: str | None = None,
    regex_patterns: str | None = None,
    presets: str | None = None,
    allow_list: str | None = None,
    exempt_roles: str | None = None,
    exempt_channels: str | None = None,
    enabled: bool = False,
    custom_message: str | None = None,
    mention_limit: int | None = None,
    mention_raid_protection: bool = False,
) -> None:
    guild = await _get_guild(ctx)
    if guild is None:
        return
    if not isinstance(ctx.author, discord.Member):
        await _send_error(ctx, "Your server permissions couldn't be verified.")
        return
    try:
        spec = _build_spec(
            guild=guild,
            actor=ctx.author,
            name=name,
            trigger_name=trigger_type,
            actions=actions,
            alert_channel=alert_channel,
            keywords=keywords,
            regex_patterns=regex_patterns,
            presets=presets,
            allow_list=allow_list,
            exempt_roles=exempt_roles,
            exempt_channels=exempt_channels,
            enabled=enabled,
            custom_message=custom_message,
            mention_limit=mention_limit,
            mention_raid_protection=mention_raid_protection,
        )
    except ValueError as error:
        await _send_error(ctx, str(error))
        return
    await _create_spec_for_context(ctx, spec)


class _SetupTriggerSelect(discord.ui.Select):
    def __init__(self, view: _AutoModSetupView) -> None:
        self.setup_view = view
        super().__init__(
            placeholder="Choose a rule type",
            options=[
                discord.SelectOption(
                    label=trigger_type.replace("_", " ").title(),
                    value=trigger_type,
                    default=trigger_type == view.trigger_name,
                )
                for trigger_type in TRIGGER_TYPES
            ],
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.setup_view.trigger_name = self.values[0]
        await self.setup_view.refresh(interaction)


class _SetupAlertChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, view: _AutoModSetupView) -> None:
        self.setup_view = view
        super().__init__(
            channel_types=[discord.ChannelType.text],
            placeholder="Optional alert channel",
            min_values=0,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.setup_view.alert_channel = self.values[0] if self.values else None
        await self.setup_view.refresh(interaction)


class _SetupRoleSelect(discord.ui.RoleSelect):
    def __init__(self, view: _AutoModSetupView) -> None:
        self.setup_view = view
        super().__init__(
            placeholder="Optional exempt roles",
            min_values=0,
            max_values=MAX_EXEMPT_ROLES,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.setup_view.exempt_roles = list(self.values)
        await self.setup_view.refresh(interaction)


class _SetupExemptChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, view: _AutoModSetupView) -> None:
        self.setup_view = view
        super().__init__(
            placeholder="Optional exempt channels (up to 25 in this wizard)",
            min_values=0,
            max_values=25,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.setup_view.exempt_channels = list(self.values)
        await self.setup_view.refresh(interaction)


class _AutoModSetupModal(discord.ui.Modal, title="Configure AutoMod rule"):
    name = discord.ui.TextInput(
        label="Rule name",
        max_length=100,
        required=True,
    )
    filters = discord.ui.TextInput(
        label="Keywords or keyword presets",
        placeholder="Comma/newline-separated; presets: profanity, sexual_content, slurs",
        max_length=2000,
        required=False,
        style=discord.TextStyle.paragraph,
    )
    regex_patterns = discord.ui.TextInput(
        label="Rust regex patterns (one per line)",
        max_length=2000,
        required=False,
        style=discord.TextStyle.paragraph,
    )
    allow_list = discord.ui.TextInput(
        label="Allow-list exceptions",
        placeholder="Comma/newline-separated exact words or phrases",
        max_length=2000,
        required=False,
        style=discord.TextStyle.paragraph,
    )
    actions = discord.ui.TextInput(
        label="Actions",
        placeholder="block, alert, timeout=10m, interactions",
        max_length=500,
        required=True,
        default="block",
    )

    def __init__(self, setup_view: _AutoModSetupView) -> None:
        super().__init__()
        self.setup_view = setup_view
        self.name.default = setup_view.name
        self.filters.default = setup_view.filter_values
        self.regex_patterns.default = setup_view.regex_values
        self.allow_list.default = setup_view.allow_values
        self.actions.default = setup_view.action_values or "block"

    async def on_submit(self, interaction: discord.Interaction) -> None:
        view = self.setup_view
        if (
            interaction.user.id != view.actor.id
            or not isinstance(interaction.user, discord.Member)
            or not interaction.user.guild_permissions.manage_guild
        ):
            await interaction.response.send_message(
                "You need Manage Server permission to configure this rule.",
                ephemeral=True,
            )
            return
        view.name = self.name.value.strip()
        view.filter_values = self.filters.value
        view.regex_values = self.regex_patterns.value
        view.allow_values = self.allow_list.value
        view.action_values = self.actions.value
        await interaction.response.send_message(
            "Setup values saved. Review the wizard and select **Review and create**.",
            ephemeral=True,
        )
        await view.update_message()


class _ConfirmCreateView(discord.ui.View):
    def __init__(
        self,
        guild: discord.Guild,
        actor: discord.Member,
        spec: RuleSpec,
    ) -> None:
        super().__init__(timeout=60)
        self.guild = guild
        self.actor = actor
        self.spec = spec

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if (
            interaction.user.id == self.actor.id
            and isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.manage_guild
        ):
            return True
        await interaction.response.send_message(
            "Only the original moderator with Manage Server permission can confirm it.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Create rule", style=discord.ButtonStyle.success)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        await interaction.response.defer(ephemeral=True)
        try:
            rule = await _create_rule(
                self.guild,
                self.spec,
                reason=f"Created by {self.actor} via AutoMod setup",
            )
        except discord.Forbidden:
            response = "I don't have permission to create AutoMod rules."
        except discord.HTTPException as error:
            logger.warning(
                "Could not create AutoMod rule in guild %s (HTTP %s).",
                self.guild.id,
                error.status,
            )
            response = (
                "Discord couldn't create the rule. Check its values, permissions, "
                "and AutoMod limits."
            )
        else:
            response = (
                f"Created AutoMod rule **{discord.utils.escape_markdown(rule.name)}** "
                f"with ID `{rule.id}`."
            )
        await interaction.edit_original_response(
            content=response,
            embed=None,
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        self.stop()
        await interaction.response.edit_message(
            content="AutoMod setup cancelled.",
            embed=None,
            view=None,
        )


class _AutoModSetupView(discord.ui.View):
    def __init__(self, guild: discord.Guild, actor: discord.Member) -> None:
        super().__init__(timeout=180)
        self.guild = guild
        self.actor = actor
        self.trigger_name = "keyword"
        self.name = ""
        self.filter_values = ""
        self.regex_values = ""
        self.allow_values = ""
        self.action_values = "block"
        self.enabled = False
        self.alert_channel: discord.TextChannel | None = None
        self.exempt_roles: list[discord.Role] = []
        self.exempt_channels: list[discord.abc.GuildChannel] = []
        self.message: discord.Message | None = None
        self.add_item(_SetupTriggerSelect(self))
        self.add_item(_SetupAlertChannelSelect(self))
        self.add_item(_SetupRoleSelect(self))
        self.add_item(_SetupExemptChannelSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if (
            interaction.user.id == self.actor.id
            and isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.manage_guild
        ):
            return True
        await interaction.response.send_message(
            "Only the original moderator with Manage Server permission can use this setup.",
            ephemeral=True,
        )
        return False

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="AutoMod setup",
            description=(
                "Choose a native rule type, configure its fields, then review the "
                "complete configuration before creating it."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(name="Type", value=self.trigger_name, inline=True)
        embed.add_field(
            name="Name",
            value=self.name or "Not configured",
            inline=True,
        )
        embed.add_field(
            name="Alert channel",
            value=self.alert_channel.mention if self.alert_channel else "None",
            inline=True,
        )
        embed.add_field(
            name="Exempt roles",
            value=str(len(self.exempt_roles)),
            inline=True,
        )
        embed.add_field(
            name="Exempt channels",
            value=str(len(self.exempt_channels)),
            inline=True,
        )
        return embed

    async def update_message(self) -> None:
        if self.message is not None:
            await self.message.edit(
                embed=self.build_embed(),
                view=self,
                allowed_mentions=discord.AllowedMentions.none(),
            )

    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(
            embed=self.build_embed(),
            view=self,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    def build_spec(self) -> RuleSpec:
        if not self.name:
            raise ValueError("Configure a rule name before reviewing.")
        filter_kwargs: dict[str, str | None] = {
            "keywords": self.filter_values
            if self.trigger_name in {"keyword", "member_profile"}
            else None,
            "presets": self.filter_values
            if self.trigger_name == "keyword_preset"
            else None,
            "regex_patterns": self.regex_values,
            "allow_list": self.allow_values,
        }
        action_values = self.action_values or "block"
        alert_channel = (
            self.alert_channel
            if "alert" in action_values.casefold()
            else None
        )
        return _build_spec(
            guild=self.guild,
            actor=self.actor,
            name=self.name,
            trigger_name=self.trigger_name,
            actions=action_values,
            alert_channel=alert_channel,
            keywords=filter_kwargs["keywords"],
            regex_patterns=filter_kwargs["regex_patterns"],
            presets=filter_kwargs["presets"],
            allow_list=filter_kwargs["allow_list"],
            exempt_roles=",".join(str(role.id) for role in self.exempt_roles),
            exempt_channels=",".join(
                str(channel.id) for channel in self.exempt_channels
            ),
            enabled=self.enabled,
            custom_message=None,
        )

    @discord.ui.button(
        label="Configure rule",
        style=discord.ButtonStyle.primary,
        row=4,
    )
    async def configure(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        await interaction.response.send_modal(_AutoModSetupModal(self))

    @discord.ui.button(
        label="Disabled",
        style=discord.ButtonStyle.secondary,
        row=4,
    )
    async def toggle_enabled(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        self.enabled = not getattr(self, "enabled", False)
        button.label = "Enabled" if self.enabled else "Disabled"
        button.style = (
            discord.ButtonStyle.success
            if self.enabled
            else discord.ButtonStyle.secondary
        )
        await self.refresh(interaction)

    @discord.ui.button(
        label="Review and create",
        style=discord.ButtonStyle.success,
        row=4,
    )
    async def review(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        try:
            spec = self.build_spec()
        except ValueError as error:
            await interaction.response.send_message(str(error), ephemeral=True)
            return
        embed = discord.Embed(
            title="Review AutoMod rule",
            description=(
                f"**Name:** {spec.name}\n"
                f"**Trigger:** {spec.trigger.type.name}\n"
                f"**Enabled:** {spec.enabled}\n"
                f"**Actions:** {', '.join(_format_action(action) for action in spec.actions)}\n"
                f"**Keywords:** {len(spec.trigger.keyword_filter)} · "
                f"**Regex:** {len(spec.trigger.regex_patterns)} · "
                f"**Exceptions:** {len(spec.trigger.allow_list)}\n"
                f"**Exempt roles/channels:** {len(spec.exempt_roles)}/"
                f"{len(spec.exempt_channels)}"
            ),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(
            embed=embed,
            view=_ConfirmCreateView(self.guild, self.actor, spec),
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.danger,
        row=4,
    )
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        self.stop()
        await interaction.response.edit_message(
            content="AutoMod setup cancelled.",
            embed=None,
            view=None,
        )


@automod.command(name="setup", description="Open an interactive AutoMod setup wizard.")
async def automod_setup(ctx: commands.Context) -> None:
    guild = await _get_guild(ctx)
    if guild is None:
        return
    if not isinstance(ctx.author, discord.Member):
        await _send_error(ctx, "Your server permissions couldn't be verified.")
        return
    view = _AutoModSetupView(guild, ctx.author)
    view.message = await _send(ctx, embed=view.build_embed(), view=view)


@automod.command(name="rules", description="List native rules or inspect one by ID.")
async def automod_rules(
    ctx: commands.Context,
    rule_id: str | None = None,
) -> None:
    await _list_rules(ctx, rule_id)


@automod.command(name="inspect", description="Inspect a native AutoMod rule by ID.")
async def automod_inspect(ctx: commands.Context, rule_id: str) -> None:
    rule = await _fetch_rule(ctx, rule_id)
    if rule is not None:
        await _send(ctx, embed=_rule_embed(rule))


@automod.command(name="enable", description="Enable an AutoMod rule by ID.")
async def automod_enable(ctx: commands.Context, rule_id: str) -> None:
    await _set_rule_enabled(ctx, rule_id, True)


@automod.command(name="disable", description="Disable an AutoMod rule by ID.")
async def automod_disable(ctx: commands.Context, rule_id: str) -> None:
    await _set_rule_enabled(ctx, rule_id, False)


async def _set_rule_enabled(
    ctx: commands.Context,
    rule_id: str,
    enabled: bool,
) -> None:
    rule = await _fetch_rule(ctx, rule_id)
    if rule is None:
        return
    if rule.enabled == enabled:
        await _send(ctx, f"Rule `{rule.id}` is already {'enabled' if enabled else 'disabled'}.")
        return
    try:
        updated = await rule.edit(
            enabled=enabled,
            reason=f"{'Enabled' if enabled else 'Disabled'} by {ctx.author}",
        )
    except discord.Forbidden as error:
        await _report_api_error(ctx, error, "update")
        return
    except discord.HTTPException as error:
        await _report_api_error(ctx, error, "update")
        return
    await _send(ctx, f"Rule **{updated.name}** (`{updated.id}`) is now {'enabled' if enabled else 'disabled'}.")


@automod.command(name="rename", description="Rename a native AutoMod rule.")
async def automod_rename(
    ctx: commands.Context,
    rule_id: str,
    name: str,
) -> None:
    rule = await _fetch_rule(ctx, rule_id)
    if rule is None:
        return
    name = name.strip()
    scp = _parse_scp_name(rule.name)
    if scp is not None:
        name = (
            f"[SCP:{scp[0]}:{'cs' if scp[1] else 'ci'}:"
            f"{'o1' if scp[2] else 'o0'}] {name}"
        )
    if not name or len(name) > 100:
        await _send_error(ctx, "Rule names must be between 1 and 100 characters.")
        return
    try:
        updated = await rule.edit(
            name=name,
            reason=f"Renamed by {ctx.author}",
        )
    except discord.Forbidden as error:
        await _report_api_error(ctx, error, "rename")
        return
    except discord.HTTPException as error:
        await _report_api_error(ctx, error, "rename")
        return
    await _send(ctx, f"Renamed rule `{updated.id}` to **{discord.utils.escape_markdown(updated.name)}**.")


@automod.command(name="edit", description="Edit a rule's actions, exemptions, or status.")
@app_commands.describe(
    actions="Replacement actions: block, alert, timeout=10m, interactions.",
    alert_channel="Required when replacement actions include alert.",
    exempt_roles="Replacement role list; use `clear` to remove all.",
    exempt_channels="Replacement channel list; use `clear` to remove all.",
)
async def automod_edit(
    ctx: commands.Context,
    rule_id: str,
    name: str | None = None,
    actions: str | None = None,
    alert_channel: discord.TextChannel | None = None,
    custom_message: str | None = None,
    exempt_roles: str | None = None,
    exempt_channels: str | None = None,
    enabled: bool | None = None,
) -> None:
    rule = await _fetch_rule(ctx, rule_id)
    if rule is None:
        return
    if all(
        value is None
        for value in (name, actions, alert_channel, custom_message, exempt_roles, exempt_channels, enabled)
    ):
        await _send_error(ctx, "Provide at least one setting to edit.")
        return
    if not isinstance(ctx.author, discord.Member) or ctx.guild is None:
        await _send_error(ctx, "Your server permissions couldn't be verified.")
        return
    changes: dict[str, object] = {}
    if name is not None:
        clean_name = name.strip()
        scp = _parse_scp_name(rule.name)
        if scp is not None:
            clean_name = (
                f"[SCP:{scp[0]}:{'cs' if scp[1] else 'ci'}:"
                f"{'o1' if scp[2] else 'o0'}] {clean_name}"
            )
        if not clean_name or len(clean_name) > 100:
            await _send_error(ctx, "Rule names must be between 1 and 100 characters.")
            return
        changes["name"] = clean_name
    if actions is not None:
        effective_alert = alert_channel
        if effective_alert is None and any(
            action.type is discord.AutoModRuleActionType.send_alert_message
            for action in rule.actions
        ):
            alert_id = next(
                action.channel_id
                for action in rule.actions
                if action.type is discord.AutoModRuleActionType.send_alert_message
            )
            channel = ctx.guild.get_channel(alert_id)
            if isinstance(channel, discord.TextChannel):
                effective_alert = channel
        try:
            changes["actions"] = _build_actions(
                actions,
                guild=ctx.guild,
                actor=ctx.author,
                trigger_type=rule.trigger.type,
                alert_channel=effective_alert,
                custom_message=custom_message,
            )
        except ValueError as error:
            await _send_error(ctx, str(error))
            return
    elif custom_message is not None:
        await _send_error(ctx, "Provide replacement `actions` to change the block message.")
        return
    if exempt_roles is not None:
        try:
            changes["exempt_roles"] = _parse_entities(
                exempt_roles,
                guild=ctx.guild,
                roles=True,
            )
        except ValueError as error:
            await _send_error(ctx, str(error))
            return
    if exempt_channels is not None:
        try:
            changes["exempt_channels"] = _parse_entities(
                exempt_channels,
                guild=ctx.guild,
                roles=False,
            )
        except ValueError as error:
            await _send_error(ctx, str(error))
            return
    if enabled is not None:
        changes["enabled"] = enabled
    try:
        updated = await rule.edit(
            **changes,
            reason=f"Edited by {ctx.author}",
        )
    except discord.Forbidden as error:
        await _report_api_error(ctx, error, "edit")
        return
    except discord.HTTPException as error:
        await _report_api_error(ctx, error, "edit")
        return
    await _send(ctx, f"Updated AutoMod rule **{updated.name}** (`{updated.id}`).")


class _DeleteRuleView(discord.ui.View):
    def __init__(self, guild: discord.Guild, rule_id: int, owner_id: int) -> None:
        super().__init__(timeout=60)
        self.guild = guild
        self.rule_id = rule_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if (
            interaction.user.id == self.owner_id
            and isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.manage_guild
        ):
            return True
        await interaction.response.send_message(
            "Only the original moderator with Manage Server permission can confirm deletion.",
            ephemeral=True,
        )
        return False

    @discord.ui.button(label="Delete rule", style=discord.ButtonStyle.danger)
    async def confirm(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        await interaction.response.defer(ephemeral=True)
        try:
            rules = await self.guild.fetch_automod_rules()
            rule = next((item for item in rules if item.id == self.rule_id), None)
            if rule is None:
                message = "That AutoMod rule no longer exists."
            else:
                await rule.delete(reason=f"Deleted by {interaction.user}")
                message = f"Deleted AutoMod rule `{self.rule_id}`."
        except discord.Forbidden:
            message = "I don't have permission to delete AutoMod rules."
        except discord.HTTPException as error:
            logger.warning(
                "Could not delete AutoMod rule %s in guild %s (HTTP %s).",
                self.rule_id,
                self.guild.id,
                error.status,
            )
            message = "Discord couldn't delete that AutoMod rule."
        await interaction.edit_original_response(
            content=message,
            embed=None,
            view=None,
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        del button
        self.stop()
        await interaction.response.edit_message(
            content="AutoMod rule deletion cancelled.",
            embed=None,
            view=None,
        )


@automod.command(name="delete", description="Delete a native AutoMod rule by ID.")
async def automod_delete(ctx: commands.Context, rule_id: str) -> None:
    rule = await _fetch_rule(ctx, rule_id)
    if rule is None or ctx.guild is None:
        return
    await _send(
        ctx,
        f"Delete **{discord.utils.escape_markdown(rule.name)}** (`{rule.id}`)?",
        view=_DeleteRuleView(ctx.guild, rule.id, ctx.author.id),
    )


@automod.group(
    name="filter",
    description="Manage filters on an existing native AutoMod rule.",
    invoke_without_command=True,
)
async def automod_filter(ctx: commands.Context) -> None:
    await _send_error(ctx, "Use `automod filter add`, `remove`, or `list`.")


@automod_filter.command(name="add", description="Add keywords or regex patterns.")
@app_commands.choices(filter_type=FILTER_CHOICES)
@app_commands.describe(
    values="Keywords separated by commas/newlines; regex patterns by newlines/semicolons.",
)
async def automod_filter_add(
    ctx: commands.Context,
    rule_id: str,
    filter_type: str,
    values: str,
) -> None:
    await _edit_rule_filter(ctx, rule_id, filter_type, values, add=True)


@automod_filter.command(name="remove", description="Remove keywords or regex patterns.")
@app_commands.choices(filter_type=FILTER_CHOICES)
@app_commands.describe(values="The exact keyword or regex pattern values to remove.")
async def automod_filter_remove(
    ctx: commands.Context,
    rule_id: str,
    filter_type: str,
    values: str,
) -> None:
    await _edit_rule_filter(ctx, rule_id, filter_type, values, add=False)


async def _edit_rule_filter(
    ctx: commands.Context,
    rule_id: str,
    filter_type: str,
    values_text: str,
    *,
    add: bool,
) -> None:
    rule = await _fetch_rule(ctx, rule_id)
    if rule is None:
        return
    if rule.trigger.type not in (
        discord.AutoModRuleTriggerType.keyword,
        discord.AutoModRuleTriggerType.member_profile,
    ):
        await _send_error(
            ctx,
            "Only keyword and member_profile rules support keyword and regex filters.",
        )
        return
    if filter_type.casefold() == "keyword":
        values = _csv_values(values_text)
        current = list(rule.trigger.keyword_filter)
        maximum = MAX_KEYWORDS
        max_length = MAX_KEYWORD_LENGTH
        field_name = "keywords"
    elif filter_type.casefold() == "regex":
        values = _regex_values(values_text)
        current = list(rule.trigger.regex_patterns)
        maximum = MAX_REGEX_PATTERNS
        max_length = MAX_REGEX_LENGTH
        field_name = "regex patterns"
    else:
        await _send_error(ctx, "Filter type must be `keyword` or `regex`.")
        return
    if not values:
        await _send_error(ctx, "Provide at least one filter value.")
        return
    if any(len(value) > max_length for value in values):
        await _send_error(
            ctx,
            f"Each {field_name} entry must be {max_length} characters or fewer.",
        )
        return
    updated, removed, unchanged = _copy_values_for_matching(
        current,
        values,
        add=add,
    )
    if add and len(updated) > maximum:
        await _send_error(ctx, f"This rule can contain at most {maximum} {field_name}.")
        return
    if add and not any(value.casefold() not in {item.casefold() for item in current} for value in values):
        await _send(ctx, f"All requested {field_name} entries are already present.")
        return
    if not add and not removed:
        await _send(
            ctx,
            "None of those entries were found: " + ", ".join(f"`{item}`" for item in unchanged),
        )
        return
    trigger = _clone_trigger(
        rule.trigger,
        keyword_filter=updated if field_name == "keywords" else None,
        regex_patterns=updated if field_name == "regex patterns" else None,
    )
    try:
        await rule.edit(
            trigger=trigger,
            reason=f"{'Added to' if add else 'Removed from'} AutoMod filters by {ctx.author}",
        )
    except discord.Forbidden as error:
        await _report_api_error(ctx, error, "filter update")
        return
    except discord.HTTPException as error:
        await _report_api_error(ctx, error, "filter update")
        return
    verb = "Added" if add else "Removed"
    response = f"{verb} {len(updated) - len(current) if add else len(removed)} {field_name}."
    if unchanged:
        response += " Not found/already present: " + ", ".join(
            f"`{item}`" for item in unchanged
        )
        response += "."
    await _send(ctx, response)


@automod_filter.command(
    name="list",
    description="List a rule's keywords and regex patterns.",
)
@app_commands.choices(filter_type=FILTER_CHOICES)
async def automod_filter_list(
    ctx: commands.Context,
    rule_id: str,
    filter_type: str | None = None,
) -> None:
    rule = await _fetch_rule(ctx, rule_id)
    if rule is None:
        return
    if rule.trigger.type not in (
        discord.AutoModRuleTriggerType.keyword,
        discord.AutoModRuleTriggerType.member_profile,
    ):
        await _send_error(ctx, "This rule type has no keyword or regex filters.")
        return
    pages: list[discord.Embed] = []
    if filter_type is None or filter_type.casefold() == "keyword":
        values = [f"`{value}`" for value in rule.trigger.keyword_filter]
        pages.extend(
            _make_text_pages(
                f"Keywords for {rule.name} ({rule.id})",
                values,
            )
        )
    if filter_type is None or filter_type.casefold() == "regex":
        values = [f"`{value}`" for value in rule.trigger.regex_patterns]
        pages.extend(
            _make_text_pages(
                f"Regex patterns for {rule.name} ({rule.id})",
                values,
            )
        )
    if not pages:
        await _send_error(ctx, "Filter type must be `keyword` or `regex`.")
        return
    await _show_pages(ctx, pages)


@automod.command(
    name="create-scp",
    description="Create a keyword rule with false-positive-aware matching.",
)
@app_commands.choices(matching_mode=MODE_CHOICES)
@app_commands.describe(
    blocked_terms="Terms separated by commas or newlines.",
    exceptions="Optional exact words/phrases for Discord's native allow-list.",
    actions="Comma-separated actions: block, alert, timeout=10m, interactions.",
)
async def automod_create_scp(
    ctx: commands.Context,
    name: str,
    blocked_terms: str,
    matching_mode: str = "balanced",
    case_sensitive: bool = False,
    allow_word_boundaries: bool = True,
    detect_obfuscation: bool | None = None,
    detect_separators: bool | None = None,
    allow_exceptions: bool = True,
    exceptions: str | None = None,
    actions: str = "block",
    alert_channel: discord.TextChannel | None = None,
    exempt_roles: str | None = None,
    exempt_channels: str | None = None,
    enabled: bool = False,
) -> None:
    guild = await _get_guild(ctx)
    if guild is None:
        return
    if not isinstance(ctx.author, discord.Member):
        await _send_error(ctx, "Your server permissions couldn't be verified.")
        return
    name = name.strip()
    if not name:
        await _send_error(ctx, "Provide a name for the SCP AutoMod rule.")
        return
    mode = matching_mode.casefold()
    if mode not in {"strict", "balanced", "aggressive"}:
        await _send_error(ctx, "Matching mode must be strict, balanced, or aggressive.")
        return
    terms = _csv_values(blocked_terms)
    if not terms:
        await _send_error(ctx, "Provide at least one blocked term.")
        return
    if len(terms) > MAX_KEYWORDS:
        await _send_error(ctx, f"A rule can contain at most {MAX_KEYWORDS} blocked terms.")
        return
    if any(len(term) > MAX_KEYWORD_LENGTH or "*" in term for term in terms):
        await _send_error(
            ctx,
            "Blocked terms must be 60 characters or fewer and cannot contain `*`.",
        )
        return
    obfuscation = (
        mode != "strict" if detect_obfuscation is None else detect_obfuscation
    )
    separators = (
        mode in {"balanced", "aggressive"}
        if detect_separators is None
        else detect_separators
    )
    exception_values = _csv_values(exceptions) if allow_exceptions else []
    if exceptions and not allow_exceptions:
        await _send_error(ctx, "Enable allow_exceptions to configure exceptions.")
        return
    if case_sensitive and exception_values:
        await _send_error(
            ctx,
            "Discord's native AutoMod allow-list is case-insensitive, so it cannot "
            "safely be combined with case-sensitive matching. Disable case_sensitive "
            "or omit exceptions.",
        )
        return
    try:
        if len(exception_values) > MAX_ALLOW_LIST:
            raise ValueError(f"A keyword rule allows at most {MAX_ALLOW_LIST} exceptions.")
        if any(len(value) > MAX_KEYWORD_LENGTH for value in exception_values):
            raise ValueError(
                f"Exceptions must be {MAX_KEYWORD_LENGTH} characters or fewer."
            )
        pattern_values: list[str] = []
        if case_sensitive or obfuscation or separators:
            if len(terms) > MAX_REGEX_PATTERNS:
                raise ValueError(
                    f"Discord allows at most {MAX_REGEX_PATTERNS} regex patterns per "
                    "rule; split these terms across multiple SCP rules."
                )
            pattern_values = [
                _scp_pattern(
                    term,
                    mode=mode,
                    case_sensitive=case_sensitive,
                    word_boundaries=allow_word_boundaries,
                    detect_obfuscation=obfuscation,
                    detect_separators=separators,
                )
                for term in terms
            ]
        keyword_values = (
            []
            if case_sensitive
            else (
                terms
                if allow_word_boundaries
                else [f"*{term}*" for term in terms]
            )
        )
        name_prefix = (
            f"[SCP:{mode}:{'cs' if case_sensitive else 'ci'}:"
            f"{'o1' if obfuscation else 'o0'}] "
        )
        spec = _build_spec(
            guild=guild,
            actor=ctx.author,
            name=f"{name_prefix}{name.strip()}",
            trigger_name="keyword",
            actions=actions,
            alert_channel=alert_channel,
            keywords=",".join(keyword_values),
            regex_patterns="\n".join(pattern_values),
            presets=None,
            allow_list=",".join(exception_values),
            exempt_roles=exempt_roles,
            exempt_channels=exempt_channels,
            enabled=enabled,
            custom_message=None,
        )
    except ValueError as error:
        await _send_error(ctx, str(error))
        return
    created = await _create_spec_for_context(ctx, spec, operation="create SCP rule")
    if created is not None:
        await _send(
            ctx,
            "The rule uses Discord's native AutoMod filters. Unicode normalization "
            "and visually similar character handling are applied by the bot-side "
            "supplement; Discord's native regex engine cannot provide those guarantees.",
        )


def _preview_scp(rule: discord.AutoModRule, text: str) -> str:
    match, exception, match_type = _evaluate_scp(rule, text)
    if exception is not None:
        return (
            f"**Would not trigger**; exception `{exception}` matched an exact "
            "word/phrase boundary. Exception applied: **yes**."
        )
    if match is not None:
        reasons = {
            "exact keyword": "whole-word keyword matched",
            "substring/wildcard": "keyword uses a wildcard/substring strategy",
            "exact regex": "regex matched the sample",
            "obfuscated regex": "regex matched a configured substitution or separator pattern",
        }
        return (
            f"**Would trigger**; matched `{match}`.\n"
            f"Match type: **{match_type}** — {reasons[match_type]}. "
            "Exception applied: **no**."
        )
    return (
        "**Would not trigger** in the local preview. Match type: **none**. "
        "Exception applied: **no**."
    )


async def _test_scp(ctx: commands.Context, rule_id: str, samples: str) -> None:
    rule = await _fetch_rule(ctx, rule_id)
    if rule is None:
        return
    if (
        _parse_scp_name(rule.name) is None
        or rule.trigger.type is not discord.AutoModRuleTriggerType.keyword
    ):
        await _send_error(ctx, "SCP preview requires a rule created by `automod create-scp`.")
        return
    values = [line.strip() for line in samples.splitlines() if line.strip()]
    if not values:
        await _send_error(ctx, "Provide one phrase or multiple newline-separated samples.")
        return
    if len(values) > 20:
        await _send_error(ctx, "Test at most 20 samples at a time.")
        return
    results = [
        f"**{discord.utils.escape_markdown(value[:150])}**\n{_preview_scp(rule, value)}"
        for value in values
    ]
    embed = discord.Embed(
        title=f"SCP preview for {rule.name} (`{rule.id}`)",
        description="\n\n".join(results)[:4000],
        color=discord.Color.blurple(),
    )
    embed.set_footer(
        text=(
            "Approximate local preview only; Discord's AutoMod engine is authoritative."
        )
    )
    await _send(ctx, embed=embed)


@automod.command(
    name="test-scp",
    description="Dry-run one or more samples against a native AutoMod rule.",
)
@app_commands.describe(
    text="A sample or up to 20 newline-separated samples.",
)
async def automod_test_scp(
    ctx: commands.Context,
    rule_id: str,
    text: str,
) -> None:
    await _test_scp(ctx, rule_id, text)


@automod.group(name="scp", description="Inspect SCP rules and manage exceptions.")
async def automod_scp(ctx: commands.Context) -> None:
    await _send_error(ctx, "Use `automod scp inspect`, `test`, or `exceptions`.")


@automod_scp.command(name="inspect", description="Inspect an SCP rule by ID.")
async def automod_scp_inspect(ctx: commands.Context, rule_id: str) -> None:
    rule = await _fetch_rule(ctx, rule_id)
    if rule is None:
        return
    if _parse_scp_name(rule.name) is None:
        await _send_error(ctx, "That rule was not created by `automod create-scp`.")
        return
    await _send(ctx, embed=_rule_embed(rule))


@automod_scp.command(name="test", description="Preview samples against an SCP rule.")
@app_commands.describe(text="A sample or up to 20 newline-separated samples.")
async def automod_scp_test(
    ctx: commands.Context,
    rule_id: str,
    text: str,
) -> None:
    await _test_scp(ctx, rule_id, text)


@automod.group(
    name="scp-exceptions",
    description="Manage native AutoMod SCP allow-list exceptions.",
    invoke_without_command=True,
)
async def automod_scp_exceptions(ctx: commands.Context) -> None:
    await _send_error(
        ctx,
        "Use `automod scp-exceptions add`, `remove`, or `list` with a rule ID.",
    )


@automod_scp_exceptions.command(name="add", description="Add exact exception words or phrases.")
async def automod_scp_exceptions_add(
    ctx: commands.Context,
    rule_id: str,
    values: str,
) -> None:
    await _edit_scp_exceptions(ctx, rule_id, values, add=True)


@automod_scp_exceptions.command(name="remove", description="Remove exact exceptions.")
async def automod_scp_exceptions_remove(
    ctx: commands.Context,
    rule_id: str,
    values: str,
) -> None:
    await _edit_scp_exceptions(ctx, rule_id, values, add=False)


async def _edit_scp_exceptions(
    ctx: commands.Context,
    rule_id: str,
    values_text: str,
    *,
    add: bool,
) -> None:
    rule = await _fetch_rule(ctx, rule_id)
    if rule is None:
        return
    if (
        _parse_scp_name(rule.name) is None
        or rule.trigger.type is not discord.AutoModRuleTriggerType.keyword
    ):
        await _send_error(ctx, "SCP exceptions require a rule created by `automod create-scp`.")
        return
    values = _csv_values(values_text)
    if not values:
        await _send_error(ctx, "Provide one or more comma-separated exception words.")
        return
    if any("*" in value or len(value) > MAX_KEYWORD_LENGTH for value in values):
        await _send_error(
            ctx,
            "Use exact exception terms of at most 60 characters; `*` wildcards "
            "are not allowed.",
        )
        return
    scp = _parse_scp_name(rule.name)
    if add and scp is not None and scp[1]:
        await _send_error(
            ctx,
            "Discord's native allow-list is case-insensitive and can't be safely "
            "combined with this case-sensitive SCP rule.",
        )
        return
    original_count = len(rule.trigger.allow_list)
    updated, removed, unchanged = _copy_values_for_matching(
        rule.trigger.allow_list,
        values,
        add=add,
    )
    limit = 1000 if rule.trigger.type is discord.AutoModRuleTriggerType.keyword_preset else MAX_ALLOW_LIST
    if add and len(updated) > limit:
        await _send_error(ctx, f"This rule allows at most {limit} exception terms.")
        return
    if add and not removed and len(updated) == len(rule.trigger.allow_list):
        await _send(ctx, "All requested exceptions are already present.")
        return
    if not add and not removed:
        await _send(ctx, "None of those exceptions were found: " + ", ".join(unchanged))
        return
    try:
        await rule.edit(
            trigger=_clone_trigger(rule.trigger, allow_list=updated),
            reason=f"{'Added' if add else 'Removed'} SCP exceptions by {ctx.author}",
        )
    except discord.Forbidden as error:
        await _report_api_error(ctx, error, "exception update")
        return
    except discord.HTTPException as error:
        await _report_api_error(ctx, error, "exception update")
        return
    response = (
        f"{'Added' if add else 'Removed'} "
        f"{len(updated) - original_count if add else len(removed)} exception(s)."
    )
    if unchanged:
        response += " Not found/already present: " + ", ".join(unchanged) + "."
    await _send(ctx, response)


@automod_scp_exceptions.command(name="list", description="List native AutoMod exceptions.")
async def automod_scp_exceptions_list(
    ctx: commands.Context,
    rule_id: str,
) -> None:
    rule = await _fetch_rule(ctx, rule_id)
    if rule is None:
        return
    if (
        _parse_scp_name(rule.name) is None
        or rule.trigger.type is not discord.AutoModRuleTriggerType.keyword
    ):
        await _send_error(ctx, "SCP exceptions require a rule created by `automod create-scp`.")
        return
    await _show_pages(
        ctx,
        _make_text_pages(
            f"Exceptions for {rule.name} ({rule.id})",
            [f"`{value}`" for value in rule.trigger.allow_list],
        ),
    )


_RULE_CACHE: dict[int, tuple[float, list[discord.AutoModRule]]] = {}
_RULE_CACHE_LOCK = asyncio.Lock()


async def _cached_guild_rules(
    guild: discord.Guild,
) -> list[discord.AutoModRule] | None:
    cached = _RULE_CACHE.get(guild.id)
    if cached is not None and time.monotonic() - cached[0] < RULE_CACHE_TTL:
        return cached[1]
    async with _RULE_CACHE_LOCK:
        cached = _RULE_CACHE.get(guild.id)
        if cached is not None and time.monotonic() - cached[0] < RULE_CACHE_TTL:
            return cached[1]
        try:
            rules = await guild.fetch_automod_rules()
        except discord.Forbidden:
            logger.warning(
                "Cannot fetch AutoMod rules for SCP filtering in guild %s.",
                guild.id,
            )
            return None
        except discord.HTTPException as error:
            logger.warning(
                "Cannot fetch AutoMod rules for SCP filtering in guild %s (HTTP %s).",
                guild.id,
                error.status,
            )
            return None
        _RULE_CACHE[guild.id] = (time.monotonic(), rules)
        return rules


def _rule_exempts_message(rule: discord.AutoModRule, message: discord.Message) -> bool:
    if message.channel.id in rule.exempt_channel_ids:
        return True
    if isinstance(message.author, discord.Member):
        return any(role.id in rule.exempt_role_ids for role in message.author.roles)
    return False


async def _execute_scp_actions(
    rule: discord.AutoModRule,
    message: discord.Message,
    matched: str,
) -> None:
    member = message.author
    message_deleted = False
    for action in rule.actions:
        if action.type is discord.AutoModRuleActionType.block_message:
            try:
                await message.delete()
                message_deleted = True
            except discord.NotFound:
                message_deleted = True
            except discord.HTTPException as error:
                logger.warning(
                    "Could not delete SCP-matched message %s in guild %s (HTTP %s).",
                    message.id,
                    message.guild.id if message.guild else "unknown",
                    error.status,
                )
            if action.custom_message and isinstance(member, discord.Member):
                try:
                    await member.send(
                        action.custom_message,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    logger.debug("Could not DM member %s about an SCP match.", member.id)
        elif action.type is discord.AutoModRuleActionType.timeout:
            if isinstance(member, discord.Member) and action.duration is not None:
                try:
                    await member.timeout(
                        action.duration,
                        reason=f"Supplemental SCP AutoMod rule {rule.id}: {matched}",
                    )
                except discord.HTTPException as error:
                    logger.warning(
                        "Could not apply SCP AutoMod timeout to member %s (HTTP %s).",
                        member.id,
                        error.status,
                    )
        elif action.type is discord.AutoModRuleActionType.send_alert_message:
            guild = message.guild
            channel = (
                guild.get_channel(action.channel_id)
                if guild is not None and action.channel_id is not None
                else None
            )
            if isinstance(channel, (discord.TextChannel, discord.Thread)):
                alert = (
                    f"Supplemental SCP AutoMod match for rule `{rule.id}` "
                    f"from {member.mention} in {message.channel.mention}.\n"
                    f"Matched: `{matched}`\n"
                    f"{message.content[:1000]}"
                )
                try:
                    await channel.send(
                        alert,
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException as error:
                    logger.warning(
                        "Could not send SCP AutoMod alert for rule %s (HTTP %s).",
                        rule.id,
                        error.status,
                    )
        elif action.type is discord.AutoModRuleActionType.block_member_interactions:
            if not message_deleted:
                try:
                    await message.delete()
                except discord.NotFound:
                    message_deleted = True
                except discord.HTTPException as error:
                    logger.warning(
                        "Could not remove SCP-matched message %s for an interaction "
                        "block in guild %s (HTTP %s).",
                        message.id,
                        message.guild.id if message.guild else "unknown",
                        error.status,
                    )
                else:
                    message_deleted = True
            logger.info(
                "Supplemental SCP rule %s cannot retroactively apply Discord's "
                "block-member-interactions action; removed the triggering message.",
                rule.id,
            )


async def on_message(bot: commands.Bot, message: discord.Message) -> None:
    del bot
    guild = message.guild
    if guild is None or message.author.bot or not message.content:
        return
    rules = await _cached_guild_rules(guild)
    if rules is None:
        return
    for rule in rules:
        if (
            not rule.enabled
            or rule.event_type is not discord.AutoModRuleEventType.message_send
            or rule.trigger.type is not discord.AutoModRuleTriggerType.keyword
            or _parse_scp_name(rule.name) is None
            or _rule_exempts_message(rule, message)
        ):
            continue
        matched, exception, _ = _evaluate_scp(rule, message.content)
        if matched is None or exception is not None:
            continue
        await _execute_scp_actions(rule, message, matched)
        break


def _invalidate_rule_cache(rule: discord.AutoModRule) -> None:
    _RULE_CACHE.pop(rule.guild.id, None)


async def on_automod_rule_create(bot: commands.Bot, rule: discord.AutoModRule) -> None:
    del bot
    _invalidate_rule_cache(rule)


async def on_automod_rule_update(
    bot: commands.Bot,
    rule: discord.AutoModRule,
) -> None:
    del bot
    _invalidate_rule_cache(rule)


async def on_automod_rule_delete(
    bot: commands.Bot,
    rule: discord.AutoModRule,
) -> None:
    del bot
    _invalidate_rule_cache(rule)


listeners: dict[str, Callable[..., object]] = {
    "on_message": on_message,
    "on_automod_rule_create": on_automod_rule_create,
    "on_automod_rule_update": on_automod_rule_update,
    "on_automod_rule_delete": on_automod_rule_delete,
}
