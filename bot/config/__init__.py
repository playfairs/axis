class DISCORD:
    PREFIX = ","
    PREFIXES = (PREFIX, "!")
    OWNER_ID = 1426711359059394662


class COGS:
    EXTENSIONS = (
        "bot.extensions.information",
        "bot.extensions.social",
        "bot.extensions.administration",
    )
    SKIP = frozenset()
