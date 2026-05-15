from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from spotify_dl.models import TrackMetadata

SourceKind = Literal["album", "playlist"]


class SourceCache:
    def __init__(self, cache_directory: Path) -> None:
        self.cache_directory = cache_directory.expanduser()

    def load(
        self,
        *,
        kind: SourceKind,
        source_id: str,
        snapshot_id: str | None = None,
    ) -> tuple[str, list[TrackMetadata]] | None:
        path = self._path(kind, source_id)
        if not path.exists():
            return None
        try:
            with path.open("r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except json.JSONDecodeError:
            return None
        if payload.get("kind") != kind or payload.get("source_id") != source_id:
            return None
        if kind == "playlist" and payload.get("snapshot_id") != snapshot_id:
            return None
        tracks = [TrackMetadata(**track) for track in payload.get("tracks", [])]
        return payload.get("source_name") or source_id, tracks

    def save(
        self,
        *,
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
            "cached_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "tracks": [asdict(track) for track in tracks],
        }
        path = self._path(kind, source_id)
        tmp = path.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        tmp.replace(path)

    def _path(self, kind: SourceKind, source_id: str) -> Path:
        return self.cache_directory / f"{kind}-{source_id}.json"


_MIME_TO_EXT: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_EXT_TO_MIME: dict[str, str] = {v: k for k, v in _MIME_TO_EXT.items()}


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

