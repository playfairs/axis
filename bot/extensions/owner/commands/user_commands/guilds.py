from bot.base.imports import (
    DEFAULT_CONTAINER_COLOR,
    app_commands,
    commands,
    discord,
)

GUILDS_PER_PAGE = 15


def _member_count(guild: discord.Guild) -> int:
    return guild.member_count if guild.member_count is not None else len(guild.members)


def _channel_count(guild: discord.Guild) -> int:
    return len(guild.channels)


def _guild_summary(guild: discord.Guild, index: int) -> str:
    name = discord.utils.escape_markdown(guild.name)[:80]
    return (
        f"**{index}.** {name} — **{_member_count(guild):,} members** · "
        f"{_channel_count(guild):,} channels · {guild.premium_subscription_count or 0:,} boosts"
    )


def _guild_details(guild: discord.Guild) -> str:
    owner = f"<@{guild.owner_id}>" if guild.owner_id is not None else "Unknown"
    channels = {
        "Text": sum(
            isinstance(channel, discord.TextChannel) for channel in guild.channels
        ),
        "Voice": sum(
            isinstance(channel, discord.VoiceChannel) for channel in guild.channels
        ),
        "Stage": sum(
            isinstance(channel, discord.StageChannel) for channel in guild.channels
        ),
        "Forum": sum(
            isinstance(channel, discord.ForumChannel) for channel in guild.channels
        ),
        "Categories": sum(
            isinstance(channel, discord.CategoryChannel) for channel in guild.channels
        ),
    }
    channel_summary = " · ".join(
        f"{name}: {count:,}" for name, count in channels.items()
    )
    created = int(guild.created_at.timestamp())
    details = (
        f"**ID:** `{guild.id}`\n"
        f"**Owner:** {owner}\n"
        f"**Created:** <t:{created}:F> (<t:{created}:R>)\n"
        f"**Members:** {_member_count(guild):,}\n"
        f"**Channels:** {len(guild.channels):,} ({channel_summary})\n"
        f"**Roles:** {len(guild.roles):,} · **Emojis:** {len(guild.emojis):,} · "
        f"**Stickers:** {len(guild.stickers):,}\n"
        f"**Boosts:** {guild.premium_subscription_count or 0:,} "
        f"(tier {guild.premium_tier})\n"
        f"**Verification:** {guild.verification_level.name.replace('_', ' ').title()}\n"
        f"**Locale:** {guild.preferred_locale}"
    )
    if guild.description:
        details += f"\n**Description:** {guild.description[:500]}"
    if guild.features:
        features = ", ".join(
            feature.replace("_", " ").title() for feature in sorted(guild.features)
        )
        details += f"\n**Features:** {features[:1000]}"
    return details


class _GuildSelect(discord.ui.Select["GuildBrowserView"]):
    def __init__(
        self,
        guilds: list[discord.Guild],
        selected_guild_id: int | None,
    ) -> None:
        super().__init__(
            placeholder="Select a server to view its details.",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=guild.name[:100],
                    value=str(guild.id),
                    description=(f"{_member_count(guild):,} members · {guild.id}")[
                        :100
                    ],
                    default=guild.id == selected_guild_id,
                )
                for guild in guilds
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, GuildBrowserView):
            raise TypeError("The guild selector is not attached to GuildBrowserView.")

        selected_guild_id = int(self.values[0])
        if view.bot.get_guild(selected_guild_id) is None:
            await interaction.response.send_message(
                "That server is no longer available to the bot.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            view=GuildBrowserView(
                view.bot,
                owner_id=view.owner_id,
                page=view.page,
                selected_guild_id=selected_guild_id,
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )


class _GuildPageButton(discord.ui.Button["GuildBrowserView"]):
    def __init__(self, direction: int, page: int, total_pages: int) -> None:
        self.direction = direction
        super().__init__(
            label="Previous" if direction < 0 else "Next",
            style=discord.ButtonStyle.secondary,
            disabled=(page == 0 if direction < 0 else page + 1 == total_pages),
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        view = self.view
        if not isinstance(view, GuildBrowserView):
            raise TypeError("The guild pagination button is not attached to its view.")

        await interaction.response.edit_message(
            view=GuildBrowserView(
                view.bot,
                owner_id=view.owner_id,
                page=view.page + self.direction,
                selected_guild_id=view.selected_guild_id,
            ),
            allowed_mentions=discord.AllowedMentions.none(),
        )


class _GuildPageIndicator(discord.ui.Button["GuildBrowserView"]):
    def __init__(self, page: int, total_pages: int) -> None:
        super().__init__(
            label=f"{page + 1}/{total_pages}",
            style=discord.ButtonStyle.secondary,
            disabled=True,
        )


class GuildBrowserView(discord.ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        *,
        owner_id: int,
        page: int = 0,
        selected_guild_id: int | None = None,
    ) -> None:
        super().__init__(timeout=900)
        self.bot = bot
        self.owner_id = owner_id
        self.selected_guild_id = selected_guild_id

        guilds = sorted(bot.guilds, key=lambda guild: (guild.name.casefold(), guild.id))
        total_pages = max(1, (len(guilds) + GUILDS_PER_PAGE - 1) // GUILDS_PER_PAGE)
        self.page = max(0, min(page, total_pages - 1))
        page_start = self.page * GUILDS_PER_PAGE
        page_guilds = guilds[page_start : page_start + GUILDS_PER_PAGE]

        content: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## Bot servers · {len(guilds):,}"),
        ]
        if page_guilds:
            page_end = page_start + len(page_guilds)
            content.append(
                discord.ui.TextDisplay(
                    f"Showing {page_start + 1:,}–{page_end:,} of {len(guilds):,}\n"
                    + "\n".join(
                        _guild_summary(guild, page_start + index + 1)
                        for index, guild in enumerate(page_guilds)
                    )
                )
            )
        else:
            content.append(discord.ui.TextDisplay("The bot is not in any servers."))

        selected_guild = (
            bot.get_guild(selected_guild_id) if selected_guild_id is not None else None
        )
        if selected_guild is not None:
            content.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.TextDisplay(
                        f"### {discord.utils.escape_markdown(selected_guild.name)}\n"
                        f"{_guild_details(selected_guild)}"
                    ),
                )
            )

        if page_guilds:
            content.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.ActionRow(_GuildSelect(page_guilds, selected_guild_id)),
                )
            )
        if total_pages > 1:
            content.append(
                discord.ui.ActionRow(
                    _GuildPageButton(-1, self.page, total_pages),
                    _GuildPageIndicator(self.page, total_pages),
                    _GuildPageButton(1, self.page, total_pages),
                )
            )

        self.add_item(
            discord.ui.Container(*content, accent_color=DEFAULT_CONTAINER_COLOR)
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True

        await interaction.response.send_message(
            "Only the owner who opened this server list can use it.",
            ephemeral=True,
        )
        return False


async def _is_owner(interaction: discord.Interaction) -> bool:
    return await interaction.client.is_owner(interaction.user)


@commands.hybrid_command(
    name="guilds",
    aliases=("servers",),
    description="Browse the servers this bot is in.",
)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.check(_is_owner)
@commands.is_owner()
async def guilds(ctx: commands.Context) -> None:
    """List the bot's servers and browse their details."""
    view = GuildBrowserView(ctx.bot, owner_id=ctx.author.id)
    if ctx.interaction is not None:
        await ctx.send(
            view=view,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    await ctx.send(
        view=view,
        allowed_mentions=discord.AllowedMentions.none(),
    )
