import os

from discord import app_commands

from api.dictionary import (
    Definition,
    DictionaryLookupError,
    lookup_merriam_webster,
)
from api.native import APITransportError
from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord


class DefinitionControls(discord.ui.ActionRow):
    async def _go_to_page(
        self,
        interaction: discord.Interaction,
        page: int,
    ) -> None:
        view = self.view
        if not isinstance(view, DefinitionView):
            raise RuntimeError("Definition controls are not attached to DefinitionView.")
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
        if not isinstance(view, DefinitionView):
            raise RuntimeError("Definition controls are not attached to DefinitionView.")
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
        if not isinstance(view, DefinitionView):
            raise RuntimeError("Definition controls are not attached to DefinitionView.")
        await self._go_to_page(interaction, view.page + 1)


class DefinitionView(discord.ui.LayoutView):
    def __init__(self, term: str, definitions: list[Definition]) -> None:
        super().__init__()
        self.term = term
        self.definitions = definitions
        self.page = 0
        self.heading = discord.ui.TextDisplay("")
        self.details = discord.ui.TextDisplay("")
        self.controls = DefinitionControls()
        self.add_item(
            discord.ui.Container(
                self.heading,
                discord.ui.Separator(),
                self.details,
                discord.ui.Separator(),
                self.controls,
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )
        self._update_page()

    def _update_page(self) -> None:
        definition = self.definitions[self.page]
        heading = (
            f"*{definition.part_of_speech}* — "
            if definition.part_of_speech
            else ""
        )
        text = definition.text
        if len(text) > 1100:
            text = f"{text[:1099].rstrip()}…"
        self.heading.content = f"## {self.term}"
        self.details.content = f"{heading}{text}"
        self.controls.page_count.label = (
            f"{self.page + 1}/{len(self.definitions)}"
        )
        self.controls.previous.disabled = self.page == 0
        self.controls.next.disabled = self.page == len(self.definitions) - 1


@commands.hybrid_command(
    name="define",
    description="Look up a word in the Merriam-Webster Collegiate Dictionary.",
)
@app_commands.describe(term="The word or phrase to look up.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def define(ctx: commands.Context, *, term: str) -> None:
    term = term.strip()
    if not term:
        await ctx.send("Enter a word or phrase to look up.")
        return
    if len(term) > 100:
        await ctx.send("Word or phrase must be 100 characters or fewer.")
        return

    api_key = os.getenv("MERRIAM_WEBSTER_API_KEY")
    if not api_key or not api_key.strip():
        await ctx.send(
            "The Merriam-Webster lookup is unavailable because "
            "`MERRIAM_WEBSTER_API_KEY` is not configured."
        )
        return

    try:
        definitions, suggestions = await lookup_merriam_webster(term, api_key)
    except DictionaryLookupError as error:
        await ctx.send(f"Couldn't look up that word: {error}")
        return
    except APITransportError:
        await ctx.send("Couldn't reach Merriam-Webster right now. Please try again.")
        return

    if not definitions:
        if suggestions:
            suggestion_text = ", ".join(
                f"`{suggestion}`" for suggestion in suggestions
            )
            response = f"No definition found for **{term}**. Did you mean {suggestion_text}?"
        else:
            response = f"No definition found for **{term}**."
        await ctx.send(response, allowed_mentions=discord.AllowedMentions.none())
        return

    await ctx.send(
        view=DefinitionView(
            term,
            definitions,
        ),
        allowed_mentions=discord.AllowedMentions.none(),
    )