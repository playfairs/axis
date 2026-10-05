import json
import re
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from api.native import request

GITHUB_REPOSITORY_API_URL = "https://api.github.com/repos/"
LAST_PAGE_LINK = re.compile(r'<([^>]+)>;\s*rel="last"')


def _last_page(link_header: str | None) -> int | None:
    if link_header is None:
        return None
    match = LAST_PAGE_LINK.search(link_header)
    if match is None:
        return None
    page_values = parse_qs(urlparse(match.group(1)).query).get("page")
    if not page_values or not page_values[0].isdecimal():
        return None
    return int(page_values[0])


async def fetch_repository(owner: str, repository: str) -> dict[str, Any]:
    from api.github import GitHubError

    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Axis Discord bot",
    }
    url = (
        f"{GITHUB_REPOSITORY_API_URL}{quote(owner, safe='')}"
        f"/{quote(repository, safe='')}"
    )
    response = await request("GET", url, headers=headers)
    if response.status == 404:
        raise GitHubError(f"GitHub repository `{owner}/{repository}` was not found.")
    if response.status != 200:
        raise GitHubError(
            f"GitHub returned HTTP status {response.status}. Please try again later."
        )

    data = json.loads(response.body)
    if not isinstance(data, dict):
        raise GitHubError("GitHub returned an invalid repository response.")
    if not isinstance(data.get("full_name"), str) or not isinstance(
        data.get("html_url"), str
    ):
        raise GitHubError("GitHub returned an incomplete repository response.")

    repository_api_url = (
        f"{GITHUB_REPOSITORY_API_URL}{quote(owner, safe='')}"
        f"/{quote(repository, safe='')}"
    )

    async def fetch_count(endpoint: str) -> int:
        separator = "&" if "?" in endpoint else "?"
        count_response = await request(
            "GET",
            f"{repository_api_url}/{endpoint}{separator}per_page=1",
            headers=headers,
        )
        if count_response.status != 200:
            raise GitHubError(
                f"GitHub could not provide the repository {endpoint} count "
                f"(HTTP status {count_response.status})."
            )
        entries = json.loads(count_response.body)
        if not isinstance(entries, list):
            raise GitHubError(
                f"GitHub returned an invalid repository {endpoint} response."
            )
        last_page = _last_page(count_response.link_header)
        if count_response.link_header and last_page is None:
            raise GitHubError(
                f"GitHub returned invalid pagination data for repository {endpoint}."
            )
        return last_page if last_page is not None else len(entries)

    data["pull_requests_count"] = await fetch_count("pulls?state=open")
    open_items = data.get("open_issues_count")
    if isinstance(open_items, int) and not isinstance(open_items, bool):
        data["open_issues_count"] = max(
            0,
            open_items - data["pull_requests_count"],
        )

    return data


__all__ = ("fetch_repository",)
