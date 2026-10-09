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

# bot.extensions.information:banner
# Show's a users banner if any.

from discord import app_commands

from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord


class BannerView(discord.ui.LayoutView):
    def __init__(self, user: discord.User, banner: discord.Asset) -> None:
        super().__init__()
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"# {user.name}"),
            discord.ui.Separator(),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    banner.with_size(4096).url,
                    description=f"{user.name}'s banner",
                )
            ),
            accent_color=DEFAULT_CONTAINER_COLOR,
        )
        self.add_item(container)


@commands.hybrid_command(
    name="banner",
    description="Show your banner or another user's banner.",
)
@app_commands.describe(user="Show's a users banner if any,")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def banner(
    ctx: commands.Context,
    user: discord.User | None = None,
) -> None:
    target = user or ctx.author
    fetched_user = await ctx.bot.fetch_user(target.id)
    if fetched_user.banner is None:
        await ctx.send(f"{target.name} doesn't have a banner.")
        return

    await ctx.send(view=BannerView(fetched_user, fetched_user.banner))
