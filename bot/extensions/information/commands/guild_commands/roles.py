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

# bot.extensions.information:roles
# List all roles in this server


from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord

ROLES_PER_PAGE = 15


class RolesControls(discord.ui.ActionRow):
    async def _go_to_page(
        self,
        interaction: discord.Interaction,
        page: int,
    ) -> None:
        view = self.view
        if not isinstance(view, RolesView):
            raise RuntimeError(
                "Roles paginator controls are not attached to RolesView."
            )

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
        if not isinstance(view, RolesView):
            raise RuntimeError(
                "Roles paginator controls are not attached to RolesView."
            )
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
        if not isinstance(view, RolesView):
            raise RuntimeError(
                "Roles paginator controls are not attached to RolesView."
            )
        await self._go_to_page(interaction, view.page + 1)

    @discord.ui.button(label="Last", style=discord.ButtonStyle.secondary)
    async def last(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = self.view
        if not isinstance(view, RolesView):
            raise RuntimeError(
                "Roles paginator controls are not attached to RolesView."
            )
        await self._go_to_page(interaction, len(view.pages) - 1)


class RolesView(discord.ui.LayoutView):
    def __init__(
        self,
        guild_name: str,
        role_count: int,
        pages: list[str],
    ) -> None:
        super().__init__()
        self.guild_name = guild_name
        self.role_count = role_count
        self.pages = pages
        self.page = 0
        self.header = discord.ui.TextDisplay("")
        self.entries = discord.ui.TextDisplay("")
        self.controls = RolesControls()
        self.container = discord.ui.Container(
            self.header,
            discord.ui.Separator(),
            self.entries,
            discord.ui.Separator(),
            self.controls,
            accent_color=DEFAULT_CONTAINER_COLOR,
        )
        self.add_item(self.container)
        self._update_page()

    def _update_page(self) -> None:
        self.header.content = (
            f"## Roles in {self.guild_name}\n**Count:** {self.role_count}"
        )
        self.entries.content = self.pages[self.page]
        self.controls.page_count.label = f"{self.page + 1}/{len(self.pages)}"
        self.controls.first.disabled = self.page == 0
        self.controls.previous.disabled = self.page == 0
        self.controls.next.disabled = self.page == len(self.pages) - 1
        self.controls.last.disabled = self.page == len(self.pages) - 1


def _chunk_role_entries(entries: list[str]) -> list[str]:
    return [
        "\n".join(entries[index : index + ROLES_PER_PAGE])
        for index in range(0, len(entries), ROLES_PER_PAGE)
    ]


@commands.command(name="roles", description="List the roles in this server.")
@commands.guild_only()
async def roles(ctx: commands.Context) -> None:
    guild = ctx.guild
    if guild is None:
        await ctx.send("This command can not be used in DMs")
        return

    guild_roles = list(reversed(guild.roles))
    entries = [f"- {role.mention} (`{role.id}`)" for role in guild_roles]
    if not entries:
        entries = ["No roles found in this server."]
    pages = _chunk_role_entries(entries)

    await ctx.send(
        view=RolesView(guild.name, len(guild_roles), pages),
        allowed_mentions=discord.AllowedMentions.none(),
    )
