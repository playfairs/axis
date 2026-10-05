class DISCORD:
    PREFIX = ","
    PREFIXES = (PREFIX, "!", ";")
    OWNER_IDS = frozenset({1426711359059394662, 816725924959354890})


class COGS:
    EXTENSIONS = (
        "bot.extensions.information",
        "bot.extensions.social",
        "bot.extensions.administration",
    )
    SKIP = frozenset()
