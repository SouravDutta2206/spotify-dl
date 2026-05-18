from __future__ import annotations

import re
from pathlib import Path

from spotify_dl.models import TrackMetadata

INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SPACE_RE = re.compile(r"\s+")


def sanitize_component(value: str, fallback: str = "Unknown") -> str:
    cleaned = INVALID_PATH_CHARS.sub("_", value).strip(" .")
    cleaned = SPACE_RE.sub(" ", cleaned)
    return cleaned or fallback


class FileSystem:
    def __init__(self, output_directory: Path) -> None:
        self.output_directory = output_directory.expanduser()

    def get_album_directory(self, track: TrackMetadata) -> Path:
        year = track.album_release_date[:4] if track.album_release_date else "Unknown"
        artist = sanitize_component(track.album_artist)
        album = sanitize_component(f"{track.album_name} ({year})")
        return self.output_directory / "Artists" / artist / album

    def get_playlist_directory(self, playlist_name: str) -> Path:
        return self.output_directory / sanitize_component(playlist_name)

    def get_playlist_mirror_path(self, track: TrackMetadata, playlist_name: str) -> Path:
        return self.get_playlist_directory(playlist_name) / f"{sanitize_component(track.title)}.mp3"

    def get_track_filename(self, track: TrackMetadata) -> str:
        prefix = (
            f"{track.disc_number}-{track.track_number:02d}"
            if track.album_total_discs > 1 or track.disc_number > 1
            else f"{track.track_number:02d}"
        )
        title = sanitize_component(track.title)
        filename = f"{prefix} - {title}.mp3"
        if len(filename) <= 200:
            return filename
        max_title_len = max(1, 200 - len(f"{prefix} - .mp3") - 1)
        return f"{prefix} - {title[:max_title_len].rstrip()}....mp3"

    def get_track_path(self, track: TrackMetadata) -> Path:
        return self.get_album_directory(track) / self.get_track_filename(track)

    def ensure_parent(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def exists(self, track: TrackMetadata) -> bool:
        return self.get_track_path(track).exists()

