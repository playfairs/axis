from bot.base.imports import DEFAULT_CONTAINER_COLOR, app_commands, commands, discord

MEMBERS_PER_PAGE = 15


class InRoleControls(discord.ui.ActionRow):
    async def _go_to_page(
        self,
        interaction: discord.Interaction,
        page: int,
    ) -> None:
        view = self.view
        if not isinstance(view, InRoleView):
            raise RuntimeError("Inrole controls are not attached to InRoleView.")

        view.page = max(0, min(page, len(view.pages) - 1))
        view._update_page()
        await interaction.response.edit_message(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="First", style=discord.ButtonStyle.secondary)
    async def first(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await self._go_to_page(interaction, 0)

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = self.view
        if not isinstance(view, InRoleView):
            raise RuntimeError("Inrole controls are not attached to InRoleView.")
        await self._go_to_page(interaction, view.page - 1)

    @discord.ui.button(label="1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_count(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        await interaction.response.defer()

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = self.view
        if not isinstance(view, InRoleView):
            raise RuntimeError("Inrole controls are not attached to InRoleView.")
        await self._go_to_page(interaction, view.page + 1)

    @discord.ui.button(label="Last", style=discord.ButtonStyle.secondary)
    async def last(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = self.view
        if not isinstance(view, InRoleView):
            raise RuntimeError("Inrole controls are not attached to InRoleView.")
        await self._go_to_page(interaction, len(view.pages) - 1)


class InRoleView(discord.ui.LayoutView):
    def __init__(
        self,
        role: discord.Role,
        member_count: int,
        pages: list[str],
    ) -> None:
        super().__init__()
        self.role = role
        self.member_count = member_count
        self.pages = pages
        self.page = 0
        self.header = discord.ui.TextDisplay("")
        self.entries = discord.ui.TextDisplay("")
        self.controls = InRoleControls()
        self.add_item(
            discord.ui.Container(
                self.header,
                discord.ui.Separator(),
                self.entries,
                discord.ui.Separator(),
                self.controls,
                accent_color=(
                    role.color if role.color.value else DEFAULT_CONTAINER_COLOR
                ),
            )
        )
        self._update_page()

    def _update_page(self) -> None:
        self.header.content = (
            f"## Members with {self.role.name}\n**Count:** {self.member_count}"
        )
        self.entries.content = self.pages[self.page]
        self.controls.page_count.label = f"{self.page + 1}/{len(self.pages)}"
        self.controls.first.disabled = self.page == 0
        self.controls.previous.disabled = self.page == 0
        self.controls.next.disabled = self.page == len(self.pages) - 1
        self.controls.last.disabled = self.page == len(self.pages) - 1


def _member_pages(members: list[discord.Member]) -> list[str]:
    entries = [
        f"{index}. {member.mention} (`{member.id}`)"
        for index, member in enumerate(members, start=1)
    ]
    if not entries:
        return ["No members have this role."]
    return [
        "\n".join(entries[index : index + MEMBERS_PER_PAGE])
        for index in range(0, len(entries), MEMBERS_PER_PAGE)
    ]


@commands.hybrid_command(
    name="inrole",
    aliases=["ir"],
    description="List the members who have a specific server role.",
)
@app_commands.describe(role="The role whose members you want to list.")
@app_commands.guild_only()
async def inrole(ctx: commands.Context, role: discord.Role) -> None:
    """List all members who have a specific role."""
    guild = ctx.guild
    if guild is None:
        await ctx.send("This command can only be used in a server.")
        return

    members = [
        member
        async for member in guild.fetch_members(limit=None)
        if role in member.roles
    ]
    members.sort(key=lambda member: (member.display_name.casefold(), member.id))

    await ctx.send(
        view=InRoleView(role, len(members), _member_pages(members)),
        allowed_mentions=discord.AllowedMentions.none(),
    )
