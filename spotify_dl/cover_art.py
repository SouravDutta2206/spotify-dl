from __future__ import annotations

import requests

from spotify_dl.logging import get_logger
from spotify_dl.models import TrackMetadata
from spotify_dl.source_cache import CoverCache

logger = get_logger("cover_art")

DEFAULT_COVER_MIME = "image/jpeg"


class CoverResolver:
    def __init__(self, cover_cache: CoverCache | None = None) -> None:
        self.cover_cache = cover_cache

    def get_or_fetch(self, track: TrackMetadata) -> tuple[bytes, str]:
        if self.cover_cache and track.album_id:
            cached = self.cover_cache.get(track.album_id)
            if cached:
                logger.debug("Cover cache hit for album %s", track.album_id)
                return cached
        if not track.album_art_url:
            return b"", DEFAULT_COVER_MIME
        data, mime = fetch_cover(track.album_art_url)
        logger.debug("Cover fetched for album %s", track.album_id)
        if self.cover_cache and track.album_id:
            self.cover_cache.put(track.album_id, data, mime)
        return data, mime

    def prefetch(self, tracks: list[TrackMetadata]) -> None:
        seen: set[str] = set()
        for track in tracks:
            if not track.album_id or not track.album_art_url or track.album_id in seen:
                continue
            seen.add(track.album_id)
            try:
                self.get_or_fetch(track)
            except Exception:
                logger.warning("Cover fetch failed for album %s", track.album_id)


def fetch_cover(url: str) -> tuple[bytes, str]:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    mime = response.headers.get("content-type", DEFAULT_COVER_MIME).split(";")[0].strip()
    return response.content, mime
