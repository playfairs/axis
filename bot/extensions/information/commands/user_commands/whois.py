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

# bot.extensions.information:whois
# Show basic information about a user.

from discord import app_commands
from bot.base.imports import commands, discord
from bot.handlers.missing_avatar import get_avatar


class WhoisView(discord.ui.LayoutView):
    def __init__(
        self,
        user: discord.User | discord.Member,
        banner: discord.Asset | None,
    ) -> None:
        super().__init__()
        display_name = (
            user.display_name
            if isinstance(user, discord.Member)
            else user.global_name or user.name
        )
        details = discord.ui.TextDisplay(
            f"> **Display name**: {display_name}\n"
            f"> **Username**: {user.name}\n"
            f"> **User ID**: `{user.id}`\n"
            f"> **Created**: <t:{int(user.created_at.timestamp())}:D> "
            f"- <t:{int(user.created_at.timestamp())}:R>\n"
            f"> **Mutual servers**: {len(user.mutual_guilds)}\n"
            f"> **Type**: {'Bot' if user.bot else 'User'}"
        )
        container_items: list[discord.ui.Item] = [
            discord.ui.TextDisplay(f"## @{user.name} ({user.display_name})"),
            discord.ui.Separator(),
            discord.ui.Section(
                details,
                accessory=discord.ui.Thumbnail(
                    get_avatar(user).url,
                    description=f"{user.name}'s avatar",
                ),
            ),
        ]

        if banner is not None:
            container_items.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.TextDisplay("**Banner:**"),
                    discord.ui.MediaGallery(
                        discord.MediaGalleryItem(
                            banner.url,
                            description=f"{user.name}'s banner",
                        )
                    ),
                )
            )

        self.add_item(discord.ui.Container(*container_items))


@commands.hybrid_command(name="whois")
@app_commands.describe(user="Show basic information about a user.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def whois(
    ctx: commands.Context,
    user: discord.User | None = None,
) -> None:
    target = user or ctx.author
    fetched_user = await ctx.bot.fetch_user(target.id)
    await ctx.send(view=WhoisView(target, fetched_user.banner))
