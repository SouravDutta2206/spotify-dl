from __future__ import annotations

import requests

from spotify_dl.models import TrackMetadata
from spotify_dl.source_cache import CoverCache

DEFAULT_COVER_MIME = "image/jpeg"


class CoverResolver:
    def __init__(self, cover_cache: CoverCache | None = None) -> None:
        self.cover_cache = cover_cache

    def get_or_fetch(self, track: TrackMetadata) -> tuple[bytes, str]:
        if self.cover_cache and track.album_id:
            cached = self.cover_cache.get(track.album_id)
            if cached:
                return cached
        if not track.album_art_url:
            return b"", DEFAULT_COVER_MIME
        data, mime = fetch_cover(track.album_art_url)
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
                pass


def fetch_cover(url: str) -> tuple[bytes, str]:
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    mime = response.headers.get("content-type", DEFAULT_COVER_MIME).split(";")[0].strip()
    return response.content, mime
