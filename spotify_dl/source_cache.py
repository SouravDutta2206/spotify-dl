from __future__ import annotations

from dataclasses import asdict, fields
from datetime import datetime, timezone
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal

from spotify_dl.json_io import read_json, write_json_atomic
from spotify_dl.models import TrackMetadata

SourceKind = Literal["album", "playlist"]
_TRACK_FIELDS = frozenset(f.name for f in fields(TrackMetadata))


def deserialize_tracks(payload: dict[str, Any]) -> list[TrackMetadata]:
    """Convert a cache payload's 'tracks' list into TrackMetadata objects."""
    return [TrackMetadata(**track) for track in payload.get("tracks", [])]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SourceCache:
    def __init__(self, cache_directory: Path) -> None:
        self.cache_directory = cache_directory.expanduser()
        self._tracks: dict[str, Any] = self._load_tracks_file()

    def read_track(self, spotify_id: str) -> tuple[TrackMetadata, str | None] | None:
        entry = self._tracks.get(spotify_id)
        if not isinstance(entry, dict):
            return None
        track_data = {k: v for k, v in entry.items() if k in _TRACK_FIELDS}
        return TrackMetadata(**track_data), entry.get("youtube-link")

    def write_track(self, track: TrackMetadata, youtube_link: str | None = None) -> None:
        old_link = self._tracks.get(track.spotify_id, {}).get("youtube-link")
        entry = asdict(track)
        entry["youtube-link"] = youtube_link if youtube_link is not None else old_link
        entry["cached_at"] = _utc_now()
        self._tracks[track.spotify_id] = entry

    def flush_tracks(self) -> None:
        payload = {
            "kind": "tracks",
            "cached_at": _utc_now(),
            "tracks": self._tracks,
        }
        write_json_atomic(self.cache_directory / "tracks.json", payload)

    def read_collection(self, kind: SourceKind, source_id: str) -> dict[str, Any] | None:
        path = self.cache_directory / f"{kind}-{source_id}.json"
        payload = read_json(path)
        if payload and payload.get("kind") == kind and payload.get("source_id") == source_id:
            return payload
        return None

    def write_collection(
        self,
        kind: SourceKind,
        source_id: str,
        source_name: str,
        tracks: list[TrackMetadata],
        snapshot_id: str | None = None,
    ) -> None:
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        payload = {
            "kind": kind,
            "source_id": source_id,
            "source_name": source_name,
            "snapshot_id": snapshot_id,
            "cached_at": _utc_now(),
            "tracks": [asdict(track) for track in tracks],
        }
        write_json_atomic(self.cache_directory / f"{kind}-{source_id}.json", payload)

    def iter_playlists(self) -> Iterator[tuple[str, Path]]:
        if not self.cache_directory.exists():
            return
        for path in sorted(self.cache_directory.glob("playlist-*.json")):
            source_id = path.name.removeprefix("playlist-").removesuffix(".json")
            if source_id:
                yield source_id, path

    def _load_tracks_file(self) -> dict[str, Any]:
        payload = read_json(self.cache_directory / "tracks.json")
        if payload and payload.get("kind") == "tracks" and isinstance(payload.get("tracks"), dict):
            return payload["tracks"]
        return {}


_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_EXT_TO_MIME: dict[str, str] = {v: k for k, v in _MIME_TO_EXT.items()}
_MIME_TO_EXT["image/jpg"] = ".jpg"


class CoverCache:
    """Disk cache for album art, stored under <cache_dir>/covers/<album_id>/cover.<ext>."""

    def __init__(self, cache_directory: Path) -> None:
        self.covers_directory = cache_directory.expanduser() / "covers"

    def get(self, album_id: str) -> tuple[bytes, str] | None:
        """Return (image_bytes, mime_type) if the cover is cached, else None."""
        folder = self.covers_directory / album_id
        if not folder.exists():
            return None
        for path in folder.iterdir():
            if path.stem == "cover":
                mime = _EXT_TO_MIME.get(path.suffix, "image/jpeg")
                return path.read_bytes(), mime
        return None

    def put(self, album_id: str, data: bytes, mime: str) -> None:
        """Save image bytes to the covers cache."""
        ext = _MIME_TO_EXT.get(mime, ".jpg")
        folder = self.covers_directory / album_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"cover{ext}").write_bytes(data)
