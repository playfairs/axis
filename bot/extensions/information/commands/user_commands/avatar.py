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


@commands.command(name="avatar", aliases=("av",))
async def avatar(
    ctx: commands.Context,
    user: discord.User | discord.Member | None = None,
) -> None:
    target = user or ctx.author
    await ctx.send(view=AvatarView(target))