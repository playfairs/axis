import json
from collections.abc import Mapping
from urllib.parse import urlsplit

import aiohttp
import jmespath
from discord import app_commands

from bot.base.imports import DEFAULT_CONTAINER_COLOR, commands, discord
from bot.errors.handlers.owner_only import application_owner_check

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
MAX_RESPONSE_BYTES = 256 * 1024
MAX_DISPLAY_BODY_CHARS = 1200
SUPPORTED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}


def _body_preview(body: str, content_type: str | None = None) -> str:
    if not body:
        return "No body."

    media_type = (content_type or "").split(";", 1)[0].strip().casefold()
    language = {
        "application/json": "json",
        "application/xml": "xml",
        "text/xml": "xml",
        "text/html": "html",
        "text/css": "css",
        "text/csv": "csv",
        "application/javascript": "js",
        "text/javascript": "js",
    }.get(media_type, "text")
    if media_type == "application/json" or media_type.endswith("+json"):
        try:
            body = json.dumps(json.loads(body), indent=2, ensure_ascii=False)
            language = "json"
        except json.JSONDecodeError:
            pass

    escaped = body.replace("```", "``\u200b`")
    truncated = len(escaped) > MAX_DISPLAY_BODY_CHARS
    if truncated:
        escaped = escaped[:MAX_DISPLAY_BODY_CHARS]
    preview = f"```{language}\n{escaped}\n```"
    if truncated:
        preview += "\n… (truncated)"
    return preview


def _format_request_data(data: object, *, provided: bool) -> str:
    if not provided:
        return "No data."
    formatted = json.dumps(data, indent=2, ensure_ascii=False)
    return _body_preview(formatted, "application/json")


class RequestResultView(discord.ui.LayoutView):
    def __init__(
        self,
        *,
        method: str,
        url: str,
        data: object,
        data_provided: bool,
        query: str | None,
        status: int | None,
        response_headers: Mapping[str, str] | None = None,
        response_body: str | None = None,
        response_content_type: str | None = None,
        error: str | None = None,
    ) -> None:
        super().__init__()
        status_label = f"`{status}`" if status is not None else "`Request failed`"
        request_details = (
            f"### Request Info\n"
            f"**Method:** `{method}`\n"
            f"**URI:** `{url[:1000]}`\n"
            f"**Status:** {status_label}"
        )
        if data_provided:
            request_details += (
                f"\n**Data:**\n{_format_request_data(data, provided=True)}"
            )
        if query:
            request_details += f"\n**JMESPath Query:** `{query[:300]}`"

        response_details = "### Response"
        if response_headers:
            selected_headers = {
                key: value
                for key, value in response_headers.items()
                if key.casefold() in {"content-type", "content-length", "location"}
            }
            if selected_headers:
                response_details += (
                    "\n**Headers**\n```json\n"
                    f"{json.dumps(selected_headers, indent=2)[:1000]}\n```"
                )
        if error:
            response_details += f"\n**Error**\n{error[:1000]}"
        elif response_body:
            response_details += (
                "\n"
                f"{_body_preview(response_body, response_content_type)}"
            )

        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(request_details),
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(response_details),
                accent_color=DEFAULT_CONTAINER_COLOR,
            )
        )


async def _send_result(
    ctx: commands.Context,
    view: RequestResultView,
) -> None:
    await ctx.send(
        view=view,
        ephemeral=False,
        allowed_mentions=discord.AllowedMentions.none(),
    )


@commands.hybrid_command(
    name="req",
    description="Send an HTTP request and inspect its response (bot owner only).",
)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(
    method="HTTP method to use.",
    url="The HTTP or HTTPS URL to request.",
    data="Optional JSON data to send as the request body.",
    query="Optional JMESPath expression to filter a JSON response.",
)
@app_commands.choices(
    method=[
        app_commands.Choice(name="GET", value="GET"),
        app_commands.Choice(name="POST", value="POST"),
        app_commands.Choice(name="PUT", value="PUT"),
        app_commands.Choice(name="PATCH", value="PATCH"),
        app_commands.Choice(name="DELETE", value="DELETE"),
    ]
)
@app_commands.check(application_owner_check)
@commands.is_owner()
async def req(
    ctx: commands.Context,
    method: str,
    url: str,
    data: str | None = None,
    query: str | None = None,
) -> None:
    method = method.upper()
    if method not in SUPPORTED_METHODS:
        await ctx.send(
            "Choose GET, POST, PUT, PATCH, or DELETE.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    parsed_url = urlsplit(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        await ctx.send(
            "The URL must be an absolute HTTP or HTTPS URL.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return
    if parsed_url.username is not None or parsed_url.password is not None:
        await ctx.send(
            "Credentials cannot be embedded in the URL.",
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return

    request_data: object | None = None
    if data is not None:
        try:
            request_data = json.loads(data)
        except json.JSONDecodeError:
            await ctx.send(
                "Data must be valid JSON.",
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return

    await ctx.defer(ephemeral=False)
    try:
        async with aiohttp.ClientSession(timeout=REQUEST_TIMEOUT) as session:
            async with session.request(
                method,
                url,
                json=request_data if data is not None else None,
                allow_redirects=True,
                max_redirects=5,
            ) as response:
                response_bytes = await response.content.read(MAX_RESPONSE_BYTES + 1)
                truncated = len(response_bytes) > MAX_RESPONSE_BYTES
                response_bytes = response_bytes[:MAX_RESPONSE_BYTES]
                response_body = response_bytes.decode(
                    response.charset or "utf-8",
                    errors="replace",
                )
                if truncated:
                    response_body += "\n… (response body truncated)"
                if query:
                    try:
                        response_data = json.loads(response_body)
                        response_body = json.dumps(
                            jmespath.search(query, response_data),
                            indent=2,
                            ensure_ascii=False,
                        )
                    except (
                        json.JSONDecodeError,
                        jmespath.exceptions.JMESPathError,
                    ) as error:
                        response_body = (
                            f"JMESPath query failed: {error}\n\n"
                            f"Original response:\n{response_body}"
                        )

                view = RequestResultView(
                    method=method,
                    url=url,
                    data=request_data,
                    data_provided=data is not None,
                    query=query,
                    status=response.status,
                    response_headers=response.headers,
                    response_body=response_body,
                    response_content_type=response.headers.get("Content-Type"),
                )
    except (aiohttp.ClientError, TimeoutError, UnicodeError, ValueError) as error:
        view = RequestResultView(
            method=method,
            url=url,
            data=request_data,
            data_provided=data is not None,
            query=query,
            status=None,
            error=f"{type(error).__name__}: {error}",
        )

    await _send_result(ctx, view)
