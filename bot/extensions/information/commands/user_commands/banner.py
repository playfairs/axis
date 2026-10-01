# bot.extensions.information:banner
# Show's a users banner if any.

from discord import app_commands
from bot.base.imports import commands, discord


class BannerView(discord.ui.LayoutView):
    def __init__(self, user: discord.User, banner: discord.Asset) -> None:
        super().__init__()
        container = discord.ui.Container(
            discord.ui.TextDisplay(f"# {user.name}"),
            discord.ui.Separator(),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(
                    banner.url,
                    description=f"{user.name}'s banner",
                )
            ),
        )
        self.add_item(container)


@commands.hybrid_command(name="banner")
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
