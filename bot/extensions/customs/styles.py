import re
from typing import Any

FONT_STYLES = (
    (3, "Cherry Bomb"),
    (4, "Chicle"),
    (6, "Museo Moderno"),
    (7, "Neo Castel"),
    (8, "Pixelify"),
    (10, "Sinistre"),
    (11, "Default (GG Sans)"),
    (12, "Zilla Slab"),
    (13, "Playpen Sans"),
    (14, "Orbitron"),
    (15, "New Rocker"),
    (16, "Kalam"),
    (17, "Hexagon"),
)
EFFECT_STYLES = (
    (1, "Solid"),
    (2, "Gradient"),
    (3, "Neon"),
    (4, "Toon"),
    (5, "Pop"),
    (6, "Glow"),
    (7, "Prism"),
    (8, "Gummy"),
)
MULTICOLOR_EFFECTS = frozenset({2, 6, 7, 8})
SINGLE_COLOR_EFFECTS = frozenset({1, 3, 4, 5})
COLOR_PATTERN = re.compile(r"(?:#|0x)?([0-9a-fA-F]{6})\Z")


def parse_hex_color(value: str) -> int | None:
    match = COLOR_PATTERN.fullmatch(value)
    return int(match.group(1), 16) if match is not None else None


def supports_color_count(effect_id: Any, color_count: int) -> bool:
    if effect_id in MULTICOLOR_EFFECTS:
        return 1 <= color_count <= 5
    if effect_id in SINGLE_COLOR_EFFECTS or effect_id is None:
        return color_count == 1
    return False


def style_name(styles: tuple[tuple[int, str], ...], value: Any) -> str:
    if value is None:
        return "Default"
    for style_id, name in styles:
        if value == style_id:
            return f"{name} (ID {style_id})"
    return f"Unsupported or unknown ID {value}"


def format_colors(colors: Any) -> str:
    if not isinstance(colors, list) or not colors:
        return "Default"
    result: list[str] = []
    for value in colors:
        if isinstance(value, int) and 0 <= value <= 0xFFFFFF:
            result.append(f"#{value:06X}")
        else:
            result.append(f"Unsupported value {value}")
    return ", ".join(result)
