import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

from api.native import APITransportError, request

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"


class LastFMError(Exception):
    pass


@dataclass(frozen=True)
class Track:
    name: str
    artist: str
    album: str | None
    album_cover: str | None


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


async def fetch_current_track(api_key: str, username: str) -> Track | None:
    body = urlencode(
        {
            "method": "user.getrecenttracks",
            "user": username,
            "api_key": api_key,
            "format": "json",
            "limit": "1",
        }
    )
    response = await request(
        "POST",
        LASTFM_API_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        body=body,
    )
    if response.status != 200:
        raise LastFMError(f"Last.fm returned HTTP status {response.status}.")
    return _current_track(json.loads(response.body))


__all__ = (
    "APITransportError",
    "LastFMError",
    "Track",
    "fetch_current_track",
)
