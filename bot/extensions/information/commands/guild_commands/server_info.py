# This file is part of Axis.
#
# Copyright (c) 2026 playfairs
#
# This work is released into the public domain under the Unlicense.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# See the UNLICENSE file for details.

# bot.extensions.information:serverinfo
# Show detailed information about the server


from bot.base.imports import (
    DEFAULT_CONTAINER_COLOR,
    app_commands,
    commands,
    discord,
)


def _channel_counts(guild: discord.Guild) -> str:
    counts = {
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
    return "\n".join(f"**{name}:** {count}" for name, count in counts.items())


class ServerInfoView(discord.ui.LayoutView):
    def __init__(self, guild: discord.Guild) -> None:
        super().__init__()
        owner = guild.get_member(guild.owner_id)
        owner_text = owner.mention if owner is not None else f"<@{guild.owner_id}>"
        details = discord.ui.TextDisplay(
            f"**ID:** `{guild.id}`\n"
            f"**Owner:** {owner_text}\n"
            f"**Created:** <t:{int(guild.created_at.timestamp())}:F> "
            f"(<t:{int(guild.created_at.timestamp())}:R>)\n"
            f"**Members:** {guild.member_count or len(guild.members):,}\n"
            f"**Roles:** {len(guild.roles):,}\n"
            f"**Emojis:** {len(guild.emojis):,} | "
            f"**Stickers:** {len(guild.stickers):,}"
        )
        settings = discord.ui.TextDisplay(
            "### Channels\n"
            f"{_channel_counts(guild)}\n\n"
            "### Server settings\n"
            f"**Verification:** {guild.verification_level.name.replace('_', ' ').title()}\n"
            f"**Content filter:** "
            f"{guild.explicit_content_filter.name.replace('_', ' ').title()}\n"
            f"**Notifications:** "
            f"{guild.default_notifications.name.replace('_', ' ').title()}\n"
            f"**Boost level:** {guild.premium_tier} "
            f"({guild.premium_subscription_count or 0} boosts)\n"
            f"**Locale:** {guild.preferred_locale}"
        )
        if guild.features:
            features = ", ".join(
                feature.replace("_", " ").title() for feature in sorted(guild.features)
            )
            settings.content += f"\n\n### Features\n{features}"

        items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## {guild.name}"),
        ]
        if guild.description:
            items.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.TextDisplay(guild.description[:4000]),
                )
            )

        items.extend((discord.ui.Separator(),))
        if guild.icon is not None:
            items.append(
                discord.ui.Section(
                    details,
                    accessory=discord.ui.Thumbnail(
                        guild.icon.url,
                        description=f"{guild.name} server icon",
                    ),
                )
            )
        else:
            items.append(details)

        items.extend(
            (
                discord.ui.Separator(),
                settings,
            )
        )
        if guild.banner is not None:
            items.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.MediaGallery(
                        discord.MediaGalleryItem(
                            guild.banner.url,
                            description=f"{guild.name} server banner",
                        )
                    ),
                )
            )

        self.add_item(
            discord.ui.Container(*items, accent_color=DEFAULT_CONTAINER_COLOR)
        )


@commands.hybrid_command(name="serverinfo", aliases=("guildinfo", "si"))
@app_commands.guild_only()
async def server_info(ctx: commands.Context) -> None:
    guild = ctx.guild
    if guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    await ctx.send(
        view=ServerInfoView(guild),
        allowed_mentions=discord.AllowedMentions.none(),
    )
