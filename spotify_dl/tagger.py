from __future__ import annotations

import shutil
from pathlib import Path

import requests
from mutagen.id3 import APIC, TALB, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK, TSRC, ID3

from spotify_dl.exceptions import TaggingError
from spotify_dl.models import TrackMetadata
from spotify_dl.source_cache import CoverCache


class Tagger:
    def __init__(self, cover_cache: CoverCache | None = None) -> None:
        self.cover_cache = cover_cache

    def tag(self, temp_mp3: Path, final_mp3: Path, track: TrackMetadata) -> Path:
        final_mp3.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_mp3), str(final_mp3))
        try:
            tags = ID3()
            tags.add(TIT2(encoding=1, text=track.title))
            tags.add(TPE1(encoding=1, text="; ".join(track.artists)))
            tags.add(TPE2(encoding=1, text=track.album_artist))
            tags.add(TALB(encoding=1, text=track.album_name))
            tags.add(TRCK(encoding=0, text=f"{track.track_number}/{track.album_total_tracks}"))
            tags.add(TPOS(encoding=0, text=f"{track.disc_number}/{track.album_total_discs}"))
            if track.album_release_date:
                tags.add(TDRC(encoding=0, text=track.album_release_date))
            if track.isrc:
                tags.add(TSRC(encoding=0, text=track.isrc))
            if track.album_art_url:
                art_data, art_mime = self._get_cover(track)
                if art_data:
                    tags.add(
                        APIC(
                            encoding=0,
                            mime=art_mime,
                            type=3,
                            desc="Cover",
                            data=art_data,
                        )
                    )
            tags.save(final_mp3, v2_version=3)
        except Exception as exc:
            raise TaggingError(f"Failed to write tags: {exc}") from exc
        return final_mp3

    def _get_cover(self, track: TrackMetadata) -> tuple[bytes, str]:
        """Return (image_bytes, mime) from the cover cache if available, else fetch live."""
        if self.cover_cache and track.album_id:
            cached = self.cover_cache.get(track.album_id)
            if cached:
                return cached

        # Cache miss or no cache — fetch live and populate the cache
        if not track.album_art_url:
            return b"", "image/jpeg"
        response = requests.get(track.album_art_url, timeout=20)
        response.raise_for_status()
        mime = response.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        data = response.content
        if self.cover_cache and track.album_id:
            self.cover_cache.put(track.album_id, data, mime)
        return data, mime
