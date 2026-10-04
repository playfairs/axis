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

# bot.extensions.information:avatar
# Show's a users avatar, or default avatar if none.

from discord import app_commands
from bot.base.imports import commands, discord
from bot.handlers.missing_avatar import get_avatar


class AvatarView(discord.ui.LayoutView):
    def __init__(self, user: discord.User | discord.Member) -> None:
        super().__init__()
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"## {user.name}'s avatar"),
            discord.ui.Separator(),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    get_avatar(user).url,
                    description=f"{user.name}'s avatar",
                )
            ),
        )
        self.add_item(container)


@commands.hybrid_command(name="avatar", aliases=("av",))
@app_commands.describe(user="Show's a users avatar, or default avatar if none.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def avatar(
    ctx: commands.Context,
    user: discord.User | discord.Member | None = None,
) -> None:
    target = user or ctx.author
    await ctx.send(view=AvatarView(target))
