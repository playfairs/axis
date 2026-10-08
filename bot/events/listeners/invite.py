import logging

from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord

logger = logging.getLogger(__name__)

ANNOUNCEMENT_CHANNEL_IDS = (
    1374163885124485171,
)
NOTIFICATION_USER_ID = 1426711359059394662


class NewGuildView(discord.ui.LayoutView):
    def __init__(
        self,
        guild: discord.Guild,
        *,
        owner: discord.Member | None,
        inviter: discord.User | discord.Member | None,
        invite_url: str | None,
    ) -> None:
        super().__init__()

        heading = "## New Guild.\n"
        if inviter is not None and invite_url is not None:
            heading += f"I was added to **{guild.name}** by {inviter.mention}."
        else:
            heading += f"I was added to **{guild.name}**."

        member_count = (
            guild.member_count
            if guild.member_count is not None
            else len(guild.members)
        )
        details = (
            f"**Owner:** {owner.mention if owner is not None else f'<@{guild.owner_id}>'}\n"
            f"**Created:** <t:{int(guild.created_at.timestamp())}:F>\n"
            f"**Members:** {member_count:,}\n"
            f"**Guild ID:** `{guild.id}`"
        )
        if inviter is not None and invite_url is not None:
            details += f"\n\n**Invite URL:** {invite_url}"

        details_display = discord.ui.TextDisplay(details)
        if guild.icon is not None:
            details_section: discord.ui.Item = discord.ui.Section(
                details_display,
                accessory=discord.ui.Thumbnail(
                    guild.icon.url,
                    description=f"{guild.name} server icon",
                ),
            )
        else:
            details_section = details_display

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(heading),
                discord.ui.Separator(),
                details_section,
                discord.ui.Separator(),
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )


async def _find_inviter(
    guild: discord.Guild,
    bot_user_id: int,
) -> discord.User | discord.Member | None:
    try:
        async for entry in guild.audit_logs(
            limit=10,
            action=discord.AuditLogAction.bot_add,
        ):
            if entry.target is not None and entry.target.id == bot_user_id:
                return entry.user
    except discord.Forbidden:
        return None
    except discord.HTTPException as error:
        logger.warning(
            "Could not find the inviter for guild %s (HTTP %s).",
            guild.id,
            error.status,
        )
    return None


async def _create_invite(guild: discord.Guild) -> str | None:
    channels = list(guild.text_channels)
    if guild.system_channel is not None:
        channels.sort(key=lambda channel: channel.id != guild.system_channel.id)

    for channel in channels:
        permissions = channel.permissions_for(guild.me) if guild.me is not None else None
        if permissions is None or not permissions.create_instant_invite:
            continue
        try:
            invite = await channel.create_invite(
                max_age=0,
                max_uses=0,
                unique=True,
                reason="Record the invite used to add the bot.",
            )
        except discord.Forbidden:
            continue
        except discord.HTTPException as error:
            logger.warning(
                "Could not create an invite for guild %s in channel %s (HTTP %s).",
                guild.id,
                channel.id,
                error.status,
            )
            continue
        return invite.url
    return None


async def _fetch_owner(guild: discord.Guild) -> discord.Member | None:
    owner = guild.owner
    if owner is not None:
        return owner
    try:
        return await guild.fetch_member(guild.owner_id)
    except discord.HTTPException as error:
        logger.warning(
            "Could not fetch the owner of guild %s (HTTP %s).",
            guild.id,
            error.status,
        )
        return None


async def _get_announcement_channel(
    bot: commands.Bot,
    channel_id: int,
) -> discord.abc.Messageable | None:
    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except discord.HTTPException as error:
            logger.warning(
                "Could not fetch announcement channel %s (HTTP %s).",
                channel_id,
                error.status,
            )
            return None
    if not isinstance(channel, discord.abc.Messageable):
        logger.warning(
            "Announcement channel %s is not messageable.",
            channel_id,
        )
        return None
    return channel


async def _send_guild_announcement(
    bot: commands.Bot,
    guild: discord.Guild,
    *,
    action: str,
) -> None:
    member_count = sum(
        server.member_count
        if server.member_count is not None
        else len(server.members)
        for server in bot.guilds
    )
    announcement = (
        f"{action} `{guild.name}`, I am now in `{len(bot.guilds)}` guilds, "
        f"serving `{member_count:,}` users."
    )
    for channel_id in ANNOUNCEMENT_CHANNEL_IDS:
        channel = await _get_announcement_channel(bot, channel_id)
        if channel is None:
            continue
        try:
            await channel.send(
                announcement,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.HTTPException as error:
            logger.warning(
                "Could not announce guild %s in channel %s (HTTP %s).",
                guild.id,
                channel_id,
                error.status,
            )


async def on_guild_join(
    bot: commands.Bot,
    guild: discord.Guild,
) -> None:
    """Announce new guild joins and DM the configured notification user."""
    if not bot.is_ready():
        return
    await _send_guild_announcement(bot, guild, action="Added to")

    inviter = await _find_inviter(guild, bot.user.id if bot.user else 0)
    invite_url = await _create_invite(guild) if inviter is not None else None
    if inviter is None or invite_url is None:
        logger.info(
            "Guild %s joined without a recorded inviter and invite URL.",
            guild.id,
        )

    owner = await _fetch_owner(guild)
    notification_user = bot.get_user(NOTIFICATION_USER_ID)
    if notification_user is None:
        try:
            notification_user = await bot.fetch_user(NOTIFICATION_USER_ID)
        except discord.HTTPException as error:
            logger.warning(
                "Could not fetch guild notification user %s (HTTP %s).",
                NOTIFICATION_USER_ID,
                error.status,
            )
            return

    try:
        await notification_user.send(
            view=NewGuildView(
                guild,
                owner=owner,
                inviter=inviter if invite_url is not None else None,
                invite_url=invite_url,
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.HTTPException as error:
        logger.warning(
            "Could not DM guild notification user %s about guild %s (HTTP %s).",
            NOTIFICATION_USER_ID,
            guild.id,
            error.status,
        )


async def on_guild_remove(
    bot: commands.Bot,
    guild: discord.Guild,
) -> None:
    """Announce when the bot leaves or is removed from a guild."""
    if not bot.is_ready():
        return
    try:
        await bot.fetch_guild(guild.id)
    except discord.NotFound:
        pass
    except discord.HTTPException as error:
        logger.warning(
            "Could not verify removal from guild %s (HTTP %s); skipping announcement.",
            guild.id,
            error.status,
        )
        return
    else:
        logger.info(
            "Ignoring guild removal event for guild %s because the bot is still a member.",
            guild.id,
        )
        return

    await _send_guild_announcement(bot, guild, action="Removed from")