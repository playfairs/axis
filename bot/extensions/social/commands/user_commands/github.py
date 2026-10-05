import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from discord import app_commands

from api.github import GitHubError, fetch_profile
from api.github_repository import fetch_repository
from api.native import APITransportError
from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord

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
        self.add_item(
            discord.ui.Container(*items, accent_color=DEFAULT_CONTAINER_COLOR)
        )


class GitHubRepositoryView(discord.ui.LayoutView):
    def __init__(self, repository: dict[str, Any]) -> None:
        super().__init__()
        full_name = repository["full_name"]
        description = repository.get("description")
        owner = repository.get("owner")
        owner_avatar = owner.get("avatar_url") if isinstance(owner, dict) else None

        heading_content = f"# {full_name}"
        if isinstance(description, str) and description:
            heading_content += f"\n{description[:3200]}"

        stats: list[str] = []
        for label, key in (
            ("Stars", "stargazers_count"),
            ("Forks", "forks_count"),
        ):
            value = repository.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value != 0:
                stats.append(f"**{label}:** {value:,}")
        if stats:
            heading_content += f"\n{' · '.join(stats)}"

        heading = discord.ui.TextDisplay(heading_content)
        if isinstance(owner_avatar, str):
            heading_section: discord.ui.Item = discord.ui.Section(
                heading,
                accessory=discord.ui.Thumbnail(
                    owner_avatar,
                    description=f"{full_name} repository owner icon",
                ),
            )
        else:
            heading_section = heading

        details: list[str] = []
        for label, key in (
            ("Language", "language"),
            ("Visibility", "visibility"),
            ("Default branch", "default_branch"),
            ("License", "license"),
            ("Created", "created_at"),
            ("Last pushed", "pushed_at"),
            ("Last updated", "updated_at"),
        ):
            value = repository.get(key)
            if key == "license":
                value = value.get("name") if isinstance(value, dict) else None
            elif key in {"created_at", "pushed_at", "updated_at"}:
                value = _discord_timestamp(value)
            if isinstance(value, str) and value:
                details.append(f"**{label}:** {value}")

        if repository.get("fork") is True:
            details.append("**Fork:** Yes")
        if repository.get("archived") is True:
            details.append("**Archived:** Yes")

        topics = repository.get("topics")
        if isinstance(topics, list):
            topic_names = [topic for topic in topics if isinstance(topic, str)]
            if topic_names:
                details.append(
                    f"**Topics:** {', '.join(f'`{topic}`' for topic in topic_names[:20])}"
                )

        items: list[discord.ui.Item] = [heading_section]
        items.append(discord.ui.Separator())
        if details:
            items.append(discord.ui.TextDisplay("\n".join(details)))
        else:
            items.append(discord.ui.TextDisplay("Repository details unavailable."))

        open_work: list[str] = []
        for label, key in (
            ("Issues", "open_issues_count"),
            ("Pull requests", "pull_requests_count"),
        ):
            value = repository.get(key)
            if isinstance(value, int) and not isinstance(value, bool) and value != 0:
                open_work.append(f"**{label}:** {value:,}")
        if open_work:
            items.extend(
                (
                    discord.ui.Separator(),
                    discord.ui.TextDisplay(f"### Open\n{' · '.join(open_work)}"),
                )
            )

        items.extend(
            (
                discord.ui.Separator(),
                discord.ui.ActionRow(
                    discord.ui.Button(
                        label="View on GitHub",
                        style=discord.ButtonStyle.link,
                        url=repository["html_url"],
                    )
                ),
            )
        )
        self.add_item(
            discord.ui.Container(*items, accent_color=DEFAULT_CONTAINER_COLOR)
        )


@commands.hybrid_command(name="github", aliases=["git", "gh"])
@app_commands.describe(username="A GitHub username or repository in owner/name format.")
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
async def github(ctx: commands.Context, username: str) -> None:
    try:
        if "/" in username:
            owner, separator, repository_name = username.partition("/")
            owner = owner.strip()
            repository_name = repository_name.strip()
            if (
                not separator
                or not owner
                or not repository_name
                or "/" in repository_name
            ):
                await ctx.send(
                    "Use a GitHub username or repository in `owner/name` format."
                )
                return
            repository = await fetch_repository(owner, repository_name)
            await ctx.send(
                view=GitHubRepositoryView(repository),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

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
