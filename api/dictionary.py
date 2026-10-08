import json
from dataclasses import dataclass
from urllib.parse import quote

from api.native import request

MERRIAM_WEBSTER_URL = "https://www.dictionaryapi.com/api/v3/references/collegiate/json/"
URBAN_DICTIONARY_URL = "https://api.urbandictionary.com/v0/define?term="


class DictionaryLookupError(Exception):
    pass


@dataclass(frozen=True)
class Definition:
    part_of_speech: str | None
    text: str


@dataclass(frozen=True)
class UrbanDefinition:
    word: str
    definition: str
    example: str | None
    author: str | None
    permalink: str | None
    thumbs_up: int
    thumbs_down: int


async def lookup_merriam_webster(
    term: str,
    api_key: str,
) -> tuple[list[Definition], list[str]]:
    response = await request(
        "GET",
        f"{MERRIAM_WEBSTER_URL}{quote(term, safe='')}?key={quote(api_key, safe='')}",
    )
    if response.status != 200:
        raise DictionaryLookupError(
            f"Merriam-Webster returned HTTP status {response.status}."
        )

    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DictionaryLookupError("Merriam-Webster returned invalid JSON.") from error
    if not isinstance(payload, list):
        raise DictionaryLookupError("Merriam-Webster returned an invalid response.")

    definitions: list[Definition] = []
    suggestions: list[str] = []
    for entry in payload:
        if isinstance(entry, str):
            suggestions.append(entry)
            continue
        if not isinstance(entry, dict):
            continue

        part_of_speech = entry.get("fl")
        if not isinstance(part_of_speech, str):
            part_of_speech = None
        short_definitions = entry.get("shortdef")
        if not isinstance(short_definitions, list):
            continue
        for text in short_definitions:
            if isinstance(text, str) and text.strip():
                definitions.append(Definition(part_of_speech, text.strip()))

    return definitions, suggestions[:5]


async def lookup_urban_dictionary(term: str) -> list[UrbanDefinition]:
    response = await request(
        "GET",
        f"{URBAN_DICTIONARY_URL}{quote(term, safe='')}",
    )
    if response.status != 200:
        raise DictionaryLookupError(
            f"Urban Dictionary returned HTTP status {response.status}."
        )

    try:
        payload = json.loads(response.body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DictionaryLookupError("Urban Dictionary returned invalid JSON.") from error
    if not isinstance(payload, dict):
        raise DictionaryLookupError("Urban Dictionary returned an invalid response.")

    entries = payload.get("list")
    if not isinstance(entries, list):
        raise DictionaryLookupError("Urban Dictionary returned an invalid response.")
    definitions: list[UrbanDefinition] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        word = entry.get("word")
        definition = entry.get("definition")
        if not isinstance(word, str) or not isinstance(definition, str):
            continue

        example = entry.get("example")
        author = entry.get("author")
        permalink = entry.get("permalink")
        thumbs_up = entry.get("thumbs_up")
        thumbs_down = entry.get("thumbs_down")
        definitions.append(
            UrbanDefinition(
                word=word,
                definition=definition,
                example=example if isinstance(example, str) and example else None,
                author=author if isinstance(author, str) and author else None,
                permalink=permalink if isinstance(permalink, str) else None,
                thumbs_up=(
                    thumbs_up
                    if isinstance(thumbs_up, int) and not isinstance(thumbs_up, bool)
                    else 0
                ),
                thumbs_down=(
                    thumbs_down
                    if isinstance(thumbs_down, int) and not isinstance(thumbs_down, bool)
                    else 0
                ),
            )
        )
    return definitions


__all__ = (
    "Definition",
    "DictionaryLookupError",
    "UrbanDefinition",
    "lookup_merriam_webster",
    "lookup_urban_dictionary",
)
