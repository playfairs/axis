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


@commands.command(name="banner")
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