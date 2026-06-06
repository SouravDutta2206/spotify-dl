from __future__ import annotations

import shutil
from pathlib import Path

from mutagen.id3 import APIC, TALB, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK, TSRC, ID3

from spotify_dl.cover_art import CoverResolver
from spotify_dl.exceptions import TaggingError
from spotify_dl.logging import get_logger
from spotify_dl.models import TrackMetadata
from spotify_dl.source_cache import CoverCache

logger = get_logger("tagger")


class Tagger:
    def __init__(self, cover_cache: CoverCache | None = None) -> None:
        self.cover_resolver = CoverResolver(cover_cache)

    def tag(self, temp_mp3: Path, final_mp3: Path, track: TrackMetadata) -> Path:
        logger.debug("Tagging: %s", track.title)
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
                art_data, art_mime = self.cover_resolver.get_or_fetch(track)
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
            tags.save(temp_mp3, v2_version=3)
        except Exception as exc:
            logger.error("Tagging failed for %s: %s", track.title, exc)
            raise TaggingError(f"Failed to write tags: {exc}") from exc
        final_mp3.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_mp3), str(final_mp3))
        logger.debug("Tagged and moved to: %s", final_mp3)
        return final_mp3
