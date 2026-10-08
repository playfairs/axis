from discord import app_commands

from api.dictionary import (
    DictionaryLookupError,
    UrbanDefinition,
    lookup_urban_dictionary,
)
from api.native import APITransportError
from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord


def _format_entry_text(text: str, limit: int) -> str:
    text = text.replace("[br]", "\n").strip()
    if len(text) > limit:
        return f"{text[: limit - 1].rstrip()}…"
    return text


class UrbanDefinitionControls(discord.ui.ActionRow):
    async def _go_to_page(
        self,
        interaction: discord.Interaction,
        page: int,
    ) -> None:
        view = self.view
        if not isinstance(view, UrbanDefinitionView):
            raise RuntimeError(
                "Urban definition controls are not attached to UrbanDefinitionView."
            )
        view.page = max(0, min(page, len(view.definitions) - 1))
        view._update_page()
        await interaction.response.edit_message(
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        view = self.view
        if not isinstance(view, UrbanDefinitionView):
            raise RuntimeError(
                "Urban definition controls are not attached to UrbanDefinitionView."
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
        if not isinstance(view, UrbanDefinitionView):
            raise RuntimeError(
                "Urban definition controls are not attached to UrbanDefinitionView."
            )
        await self._go_to_page(interaction, view.page + 1)


class UrbanDefinitionView(discord.ui.LayoutView):
    def __init__(self, definitions: list[UrbanDefinition]) -> None:
        super().__init__()
        self.definitions = definitions
        self.page = 0
        self.heading = discord.ui.TextDisplay("")
        self.details = discord.ui.TextDisplay("")
        self.author = discord.ui.TextDisplay("")
        self.controls = UrbanDefinitionControls()
        self.add_item(
            discord.ui.Container(
                self.heading,
                discord.ui.Separator(),
                self.details,
                discord.ui.Separator(),
                self.author,
                discord.ui.Separator(),
                self.controls,
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )
        self._update_page()

    def _update_page(self) -> None:
        definition = self.definitions[self.page]
        details = _format_entry_text(definition.definition, 1600)
        if definition.example:
            details += (
                f"\n\n**Example**\n{_format_entry_text(definition.example, 900)}"
            )
        self.heading.content = f"## {definition.word}"
        self.details.content = details
        self.author.content = f"Added by **{definition.author or 'Unknown'}**"
        self.controls.page_count.label = f"{self.page + 1}/{len(self.definitions)}"
        self.controls.previous.disabled = self.page == 0
        self.controls.next.disabled = self.page == len(self.definitions) - 1


@commands.hybrid_command(
    name="urban",
    description="Look up a word or phrase in Urban Dictionary.",
)
@app_commands.describe(term="The word or phrase to look up.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def urban(ctx: commands.Context, *, term: str) -> None:
    term = term.strip()
    if not term:
        await ctx.send("Enter a word or phrase to look up.")
        return
    if len(term) > 100:
        await ctx.send("Word or phrase must be 100 characters or fewer.")
        return

    try:
        definitions = await lookup_urban_dictionary(term)
    except DictionaryLookupError as error:
        await ctx.send(f"Couldn't look up that phrase: {error}")
        return
    except APITransportError:
        await ctx.send("Couldn't reach Urban Dictionary right now. Please try again.")
        return

    if not definitions:
        await ctx.send(
            f"No Urban Dictionary definition found for **{term}**.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    await ctx.send(
        view=UrbanDefinitionView(definitions),
        allowed_mentions=discord.AllowedMentions.none(),
    )
