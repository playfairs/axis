from dataclasses import dataclass

from bot.config import COGS, DISCORD


@dataclass(frozen=True)
class BotConfig:
    command_prefixes: tuple[str, ...] = DISCORD.PREFIXES
    owner_id: int = DISCORD.OWNER_ID
    extensions: tuple[str, ...] = COGS.EXTENSIONS
    skipped_extensions: frozenset[str] = COGS.SKIP
