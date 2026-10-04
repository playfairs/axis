import json
import re
from datetime import UTC, date, datetime, timedelta
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote

from loguru import logger

from api.native import APITransportError, request

GITHUB_API_URL = "https://api.github.com/users/"
GITHUB_CONTRIBUTIONS_URL = "https://github.com/users/{}/contributions"
CONTRIBUTION_COUNT = re.compile(r"([\d,]+)\s+contributions?\s+on\b")
NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')


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
                    self.daily_counts[day_date] = int(match.group(1).replace(",", ""))
        self._tooltip_id = None
        self._tooltip_text = []


async def _fetch_contributions_last_year(
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
        response = await request("GET", url)
        if response.status != 200:
            raise GitHubError(
                "GitHub could not provide the contribution chart."
                f"(HTTP status {response.status})."
            )

        calendar = _ContributionCalendarParser()
        calendar.feed(response.body.decode("utf-8"))
        calendar.close()
        for contribution_date, count in calendar.daily_counts.items():
            if first_day <= contribution_date <= today:
                parsed_days.add(contribution_date)
                total += count
    if parsed_days != expected_days:
        raise GitHubError("GitHub returned an incomplete contribution chart.")
    return total


async def _add_contributions_last_year(
    profile: dict[str, Any],
    username: str,
) -> None:
    try:
        contribution_count = await _fetch_contributions_last_year(
            username,
            datetime.now(UTC).date(),
        )
    except (
        GitHubError,
        APITransportError,
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


def _next_page(link_header: str | None) -> str | None:
    if link_header is None:
        return None
    match = NEXT_LINK.search(link_header)
    return match.group(1) if match is not None else None


async def fetch_profile(username: str) -> dict[str, Any]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Axis Discord bot",
    }
    response = await request(
        "GET",
        f"{GITHUB_API_URL}{quote(username, safe='')}",
        headers=headers,
    )
    if response.status == 404:
        raise GitHubError(f"GitHub user `{username}` was not found.")
    if response.status != 200:
        raise GitHubError(
            f"GitHub returned HTTP status {response.status}. Please try again later."
        )
    profile = json.loads(response.body)
    if not isinstance(profile, dict):
        raise GitHubError("GitHub returned an invalid profile response.")
    login = profile.get("login")
    if not isinstance(login, str):
        raise GitHubError("GitHub returned an incomplete profile response.")

    orgs_url = f"{GITHUB_API_URL}{quote(login, safe='')}/orgs?per_page=100"
    org_count = 0
    while orgs_url:
        response = await request("GET", orgs_url, headers=headers)
        if response.status != 200:
            raise GitHubError(
                f"GitHub returned HTTP status {response.status} "
                "while fetching organizations."
            )
        organizations = json.loads(response.body)
        if not isinstance(organizations, list):
            raise GitHubError("GitHub returned an invalid organizations list.")
        org_count += len(organizations)
        orgs_url = _next_page(response.link_header) or ""

    profile["public_orgs"] = org_count
    await _add_contributions_last_year(profile, login)
    return profile


__all__ = ("APITransportError", "GitHubError", "fetch_profile")
