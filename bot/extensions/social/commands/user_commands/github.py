import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from discord import app_commands

from api.github import GitHubError, fetch_profile
from api.native import APITransportError
from bot.base.imports import commands, discord

GITHUB_ORG_MENTION = re.compile(r"@[A-Za-z0-9-]+")


def _link_company_orgs(company: str) -> str:
    return GITHUB_ORG_MENTION.sub(
        lambda match: (
            f"[{match.group()}](https://github.com/{quote(match.group()[1:], safe='')})"
        ),
        company,
    )


def _discord_timestamp(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    timestamp = int(parsed.timestamp())
    return f"<t:{timestamp}:F>"


class GitHubView(discord.ui.LayoutView):
    def __init__(self, profile: dict[str, Any]) -> None:
        super().__init__()
        login = profile["login"]
        heading = f"# @{login}"
        bio = profile.get("bio")
        avatar_url = profile.get("avatar_url")
        heading_lines = [heading]
        if isinstance(bio, str) and bio:
            heading_lines.append(f'-# "{bio[:3500]}"')

        follow_stats: list[str] = []
        for label, key in (("followers", "followers"), ("following", "following")):
            value = profile.get(key)
            if isinstance(value, int) and value > 0:
                follow_stats.append(f"**{value:,}** {label}")
        if follow_stats:
            heading_lines.append(" · ".join(follow_stats))

        heading_display = discord.ui.TextDisplay("\n\n".join(heading_lines))
        if isinstance(avatar_url, str):
            heading_section: discord.ui.Item = discord.ui.Section(
                heading_display,
                accessory=discord.ui.Thumbnail(
                    avatar_url,
                    description=f"@{login}'s GitHub avatar",
                ),
            )
        else:
            heading_section = heading_display

        items: list[discord.ui.Item] = [heading_section]
        items.append(discord.ui.Separator())

        metadata: list[str] = []
        for label, key in (
            ("Joined GitHub", "created_at"),
            ("Last Updated", "updated_at"),
        ):
            value = _discord_timestamp(profile.get(key))
            if value is not None:
                metadata.append(f"**{label}:** {value}")
        account_type = profile.get("type")
        if isinstance(account_type, str) and account_type:
            metadata.append(f"**Account Type:** {account_type}")

        for label, key in (
            ("Company", "company"),
            ("Location", "location"),
            ("Website", "blog"),
            ("Email", "email"),
            ("Twitter", "twitter_username"),
        ):
            value = profile.get(key)
            if isinstance(value, str) and value:
                if key == "twitter_username":
                    value = f"@{value.lstrip('@')}"
                elif key == "company":
                    value = _link_company_orgs(value)
                metadata.append(f"**{label}:** {value}")

        if profile.get("hireable") is True:
            metadata.append("**Open to Work:** Yes")
        if metadata:
            items.append(discord.ui.TextDisplay("\n".join(metadata)))

        stats: list[str] = []
        for label, key in (
            ("Contributions", "contributions_last_year"),
            ("Repositories", "public_repos"),
            ("Followers", "followers"),
            ("Following", "following"),
            ("Orgs", "public_orgs"),
        ):
            value = profile.get(key)
            if key == "contributions_last_year" and not isinstance(value, int):
                continue
            if isinstance(value, int) and value == 0:
                continue
            stats.append(
                f"**{label}:** {value:,}"
                if isinstance(value, int)
                else f"**{label}:** N/A"
            )
        if stats:
            items.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.TextDisplay("\n".join(stats)),
                )
            )

        items.extend(
            (
                discord.ui.Separator(),
                discord.ui.ActionRow(
                    discord.ui.Button(
                        label="View on GitHub",
                        style=discord.ButtonStyle.link,
                        url=profile["html_url"],
                    ),
                ),
            )
        )
        self.add_item(discord.ui.Container(*items))


@commands.hybrid_command(name="github", aliases=["git", "gh"])
@app_commands.describe(username="The GitHub username to look up.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def github(ctx: commands.Context, username: str) -> None:
    try:
        profile = await fetch_profile(username)
    except GitHubError as error:
        await ctx.send(str(error))
        return
    except APITransportError:
        await ctx.send("Couldn't reach GitHub right now. Please try again later.")
        return
    except ValueError:
        await ctx.send("GitHub returned an invalid response. Please try again later.")
        return

    login = profile.get("login")
    profile_url = profile.get("html_url")
    if not isinstance(login, str) or not isinstance(profile_url, str):
        await ctx.send("GitHub returned an incomplete profile response.")
        return
    profile["login"] = login
    profile["html_url"] = profile_url
    await ctx.send(
        view=GitHubView(profile),
        allowed_mentions=discord.AllowedMentions.none(),
    )
