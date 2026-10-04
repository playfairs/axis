# This file is part of Axis.
#
# Copyright (c) 2026 playfairs
#
# This work is released into the public domain under the Unlicense.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
# OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
# OTHER DEALINGS IN THE SOFTWARE.
#
# See the UNLICENSE file for details.


import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from bot.base.imports import commands, discord, logger

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_USERNAME = "pdwk"
POLL_INTERVAL = 5


class LastFMError(Exception):
    pass


@dataclass(frozen=True)
class Track:
    name: str
    artist: str
    album: str | None
    album_cover: str | None

    def to_activity(self, started_at: datetime) -> discord.Activity:
        assets: dict[str, str] = {}
        if self.album_cover is not None:
            cover_url = urlsplit(self.album_cover)
            if cover_url.scheme == "https" and cover_url.netloc:
                image_path = cover_url.path
                if cover_url.query:
                    image_path = f"{image_path}?{cover_url.query}"
                assets = {
                    "large_image": f"mp:external/https/{cover_url.netloc}{image_path}",
                    "large_text": self.album or self.name,
                }
        return discord.Activity(
            type=discord.ActivityType.listening,
            name=self.artist,
            details=f"{self.artist} — {self.name}",
            state=self.name,
            status_display_type=discord.StatusDisplayType.name,
            timestamps={"start": int(started_at.timestamp() * 1000)},
            assets=assets,
        )


def _current_track(payload: Any) -> Track | None:
    if not isinstance(payload, dict):
        raise LastFMError("Last.fm returned an invalid response.")

    if "error" in payload:
        raise LastFMError(
            f"Last.fm API error {payload.get('error')}: "
            f"{payload.get('message', 'Unknown error')}"
        )

    recent_tracks = payload.get("recenttracks")
    if not isinstance(recent_tracks, dict):
        raise LastFMError("Last.fm response did not contain recent tracks.")

    track = recent_tracks.get("track")
    if isinstance(track, list):
        if not track:
            return None
        track = track[0]
    if not isinstance(track, dict):
        return None

    attributes = track.get("@attr")
    if not isinstance(attributes, dict) or attributes.get("nowplaying") != "true":
        return None

    name = track.get("name")
    artist_data = track.get("artist")
    album_data = track.get("album")
    artist = artist_data.get("#text") if isinstance(artist_data, dict) else None
    album = album_data.get("#text") if isinstance(album_data, dict) else None
    images = track.get("image")
    album_cover = None
    if isinstance(images, list):
        for image in reversed(images):
            if isinstance(image, dict):
                image_url = image.get("#text")
                if isinstance(image_url, str) and image_url:
                    album_cover = image_url
                    break

    if (
        not isinstance(name, str)
        or not name
        or not isinstance(artist, str)
        or not artist
    ):
        raise LastFMError("Last.fm returned an incomplete now-playing track.")

    return Track(
        name,
        artist,
        album if isinstance(album, str) and album else None,
        album_cover,
    )


class LastFMActivity:
    def __init__(
        self,
        bot: commands.Bot,
        api_key: str,
        username: str = LASTFM_USERNAME,
        poll_interval: int = POLL_INTERVAL,
    ) -> None:
        self.bot = bot
        self.api_key = api_key
        self.username = username
        self.poll_interval = poll_interval
        self._task: asyncio.Task[None] | None = None
        self._last_track: Track | None = None
        self._track_started_at: datetime | None = None

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="lastfm-activity")

    async def close(self) -> None:
        if self._task is None:
            return

        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None

    async def _fetch_current_track(
        self,
        session: aiohttp.ClientSession,
    ) -> Track | None:
        async with session.post(
            LASTFM_API_URL,
            data={
                "method": "user.getrecenttracks",
                "user": self.username,
                "api_key": self.api_key,
                "format": "json",
                "limit": "1",
            },
        ) as response:
            if response.status != 200:
                raise LastFMError(f"Last.fm returned HTTP status {response.status}.")
            return _current_track(await response.json(content_type=None))

    async def _run(self) -> None:
        await self.bot.wait_until_ready()
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while not self.bot.is_closed():
                try:
                    track = await self._fetch_current_track(session)
                    if track != self._last_track:
                        if track is None:
                            self._track_started_at = None
                            activity = None
                        else:
                            self._track_started_at = datetime.now(UTC)
                            activity = track.to_activity(self._track_started_at)
                        await self.bot.change_presence(activity=activity)
                        self._last_track = track
                except LastFMError as error:
                    logger.warning("Last.fm update failed: {}", error)
                except (aiohttp.ClientError, asyncio.TimeoutError) as error:
                    logger.warning(
                        "Last.fm request failed ({})",
                        type(error).__name__,
                    )
                except ValueError:
                    logger.warning("Last.fm returned invalid JSON.")
                except discord.HTTPException as error:
                    logger.warning(
                        "Failed to update Discord activity (HTTP {}).",
                        error.status,
                    )

                await asyncio.sleep(self.poll_interval)
