from typing import ClassVar


class DISCORD:
    PREFIX = ","
    PREFIXES = (PREFIX, "!", ";")
    DEV_BOT_ID = 1556469179274625124
    PREFIX_OVERRIDES: ClassVar[dict[int, tuple[str, ...]]] = {DEV_BOT_ID: ("-",)}
    OWNER_IDS = frozenset({1426711359059394662, 816725924959354890})


class COGS:
    EXTENSIONS = (
        "bot.extensions.information",
        "bot.extensions.social",
        "bot.extensions.administration",
        "bot.extensions.moderation",
        "bot.extensions.owner",
        "bot.extensions.utils",
    )
    SKIP = frozenset()
