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
from datetime import UTC, datetime
from urllib.parse import urlsplit

from api.lastfm import APITransportError, LastFMError, Track, fetch_current_track
from bot.base.imports import commands, discord, logger

LASTFM_USERNAME = "pdwk"
POLL_INTERVAL = 5


def _track_to_activity(track: Track, started_at: datetime) -> discord.Activity:
    assets: dict[str, str] = {}
    if track.album_cover is not None:
        cover_url = urlsplit(track.album_cover)
        if cover_url.scheme == "https" and cover_url.netloc:
            image_path = cover_url.path
            if cover_url.query:
                image_path = f"{image_path}?{cover_url.query}"
            assets = {
                "large_image": f"mp:external/https/{cover_url.netloc}{image_path}",
                "large_text": track.album or track.name,
            }
    return discord.Activity(
        type=discord.ActivityType.listening,
        name=track.artist,
        details=f"{track.artist} — {track.name}",
        state=track.name,
        status_display_type=discord.StatusDisplayType.name,
        timestamps={"start": int(started_at.timestamp() * 1000)},
        assets=assets,
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

    async def _run(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                track = await fetch_current_track(self.api_key, self.username)
                if track != self._last_track:
                    if track is None:
                        self._track_started_at = None
                        activity = None
                    else:
                        self._track_started_at = datetime.now(UTC)
                        activity = _track_to_activity(track, self._track_started_at)
                    await self.bot.change_presence(activity=activity)
                    self._last_track = track
            except LastFMError as error:
                logger.warning(f"Last.fm update failed: {error}")
            except APITransportError as error:
                logger.warning(f"Last.fm request failed: {error}")
            except ValueError:
                logger.warning("Last.fm returned invalid JSON.")
            except discord.HTTPException as error:
                logger.warning(f"Failed to update Discord activity (HTTP {error.status}).")

            await asyncio.sleep(self.poll_interval)
