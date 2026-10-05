from dataclasses import dataclass

from bot.config import COGS, DISCORD


@dataclass(frozen=True)
class BotConfig:
    command_prefixes: tuple[str, ...] = DISCORD.PREFIXES
    owner_ids: frozenset[int] = DISCORD.OWNER_IDS
    extensions: tuple[str, ...] = COGS.EXTENSIONS
    skipped_extensions: frozenset[str] = COGS.SKIP

    def prefixes_for(self, bot_id: int | None) -> tuple[str, ...]:
        if bot_id is not None and bot_id in DISCORD.PREFIX_OVERRIDES:
            return DISCORD.PREFIX_OVERRIDES[bot_id]
        return self.command_prefixes
