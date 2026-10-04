import asyncio
import re
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote

import aiohttp
from discord import app_commands

from bot.base.imports import commands, discord, logger

GITHUB_API_URL = "https://api.github.com/users/"
GITHUB_CONTRIBUTIONS_URL = "https://github.com/users/{}/contributions"
GITHUB_ORG_MENTION = re.compile(r"@[A-Za-z0-9-]+")
CONTRIBUTION_COUNT = re.compile(r"([\d,]+)\s+contributions?\s+on\b")


def _link_company_orgs(company: str) -> str:
    return GITHUB_ORG_MENTION.sub(
        lambda match: (
            f"[{match.group()}]"
            f"(https://github.com/{quote(match.group()[1:], safe='')})"
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


class GitHubError(Exception):
    pass


class _ContributionCalendarParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.day_dates: dict[str, date] = {}
        self.daily_counts: dict[date, int] = {}
        self._tooltip_id: str | None = None
        self._tooltip_text: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)
        classes = attributes.get("class")
        if (
            tag == "td"
            and isinstance(classes, str)
            and "ContributionCalendar-day" in classes
        ):
            day_id = attributes.get("id")
            day_date = attributes.get("data-date")
            if day_id and day_date:
                try:
                    self.day_dates[day_id] = date.fromisoformat(day_date)
                except ValueError:
                    return
        elif tag == "tool-tip":
            self._tooltip_id = attributes.get("for")
            self._tooltip_text = []

    def handle_data(self, data: str) -> None:
        if self._tooltip_id is not None:
            self._tooltip_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "tool-tip" or self._tooltip_id is None:
            return

        day_date = self.day_dates.get(self._tooltip_id)
        tooltip = " ".join(self._tooltip_text)
        if day_date is not None:
            if "No contributions" in tooltip:
                self.daily_counts[day_date] = 0
            else:
                match = CONTRIBUTION_COUNT.search(tooltip)
                if match is not None:
                    self.daily_counts[day_date] = int(
                        match.group(1).replace(",", "")
                    )
        self._tooltip_id = None
        self._tooltip_text = []


async def _fetch_contributions_last_year(
    session: aiohttp.ClientSession,
    username: str,
    today: date,
) -> int:
    first_day = today - timedelta(days=364)
    expected_days = {
        first_day + timedelta(days=offset)
        for offset in range((today - first_day).days + 1)
    }
    parsed_days: set[date] = set()
    total = 0
    for year in range(first_day.year, today.year + 1):
        from_date = date(year, 1, 1)
        to_date = date(year, 12, 31)
        url = (
            f"{GITHUB_CONTRIBUTIONS_URL.format(quote(username, safe=''))}"
            f"?from={from_date.isoformat()}&to={to_date.isoformat()}"
        )
        async with session.get(url) as response:
            if response.status != 200:
                raise GitHubError(
                    "GitHub could not provide the contribution chart."
                    f"(HTTP status {response.status})."
                )
            html = await response.text()

        calendar = _ContributionCalendarParser()
        calendar.feed(html)
        calendar.close()
        for contribution_date, count in calendar.daily_counts.items():
            if first_day <= contribution_date <= today:
                parsed_days.add(contribution_date)
                total += count
    if parsed_days != expected_days:
        raise GitHubError("GitHub returned an incomplete contribution chart.")
    return total


async def _add_contributions_last_year(
    session: aiohttp.ClientSession,
    profile: dict[str, Any],
    username: str,
) -> None:
    try:
        contribution_count = await _fetch_contributions_last_year(
            session,
            username,
            datetime.now(UTC).date(),
        )
    except (
        GitHubError,
        aiohttp.ClientError,
        asyncio.TimeoutError,
        ValueError,
        UnicodeError,
    ) as error:
        logger.warning(
            "Could not fetch GitHub contributions for {} ({}); omitting count.",
            username,
            type(error).__name__,
        )
        return

    profile["contributions_last_year"] = contribution_count


async def _fetch_profile(username: str) -> dict[str, Any]:
    timeout = aiohttp.ClientTimeout(total=15)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(
            f"{GITHUB_API_URL}{quote(username, safe='')}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Axis Discord bot",
            },
        ) as response:
            if response.status == 404:
                raise GitHubError(f"GitHub user `{username}` was not found.")
            if response.status != 200:
                raise GitHubError(
                    f"GitHub returned HTTP status {response.status}. "
                    "Please try again later."
                )
            profile = await response.json(content_type=None)

        if not isinstance(profile, dict):
            raise GitHubError("GitHub returned an invalid profile response.")
        login = profile.get("login")
        if not isinstance(login, str):
            raise GitHubError("GitHub returned an incomplete profile response.")

        orgs_url = f"{GITHUB_API_URL}{quote(login, safe='')}/orgs?per_page=100"
        org_count = 0
        while orgs_url:
            async with session.get(
                orgs_url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "axis",
                },
            ) as response:
                if response.status != 200:
                    raise GitHubError(
                        f"GitHub returned HTTP status {response.status} "
                        "while fetching organizations."
                    )
                organizations = await response.json(content_type=None)
                if not isinstance(organizations, list):
                    raise GitHubError("GitHub returned an invalid organizations list.")
                org_count += len(organizations)
                next_page = response.links.get("next")
                orgs_url = (
                    next_page["url"]
                    if next_page is not None and "url" in next_page
                    else ""
                )
        profile["public_orgs"] = org_count
        await _add_contributions_last_year(
            session,
            profile,
            login,
        )
    return profile


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
            heading_section: discord.ui.Item = (
                discord.ui.Section(
                    heading_display,
                    accessory=discord.ui.Thumbnail(
                        avatar_url,
                        description=f"@{login}'s GitHub avatar",
                    ),
                )
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
        profile = await _fetch_profile(username)
    except GitHubError as error:
        await ctx.send(str(error))
        return
    except (aiohttp.ClientError, asyncio.TimeoutError):
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