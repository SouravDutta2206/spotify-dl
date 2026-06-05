from __future__ import annotations

from pathlib import Path

from spotify_dl.exceptions import ManifestParseError
from spotify_dl.models import DownloadManifest, ManifestTrack
from spotify_dl.spotify import parse_spotify_url


_MANIFEST_SECTIONS = {
    "track": "tracks",
    "tracks": "tracks",
    "playlist": "playlists",
    "playlists": "playlists",
    "album": "albums",
    "albums": "albums",
}


def parse_download_manifest(path: str | Path) -> DownloadManifest:
    manifest_path = Path(path).expanduser()
    try:
        lines = manifest_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ManifestParseError(f"Could not read manifest file: {manifest_path}") from exc

    section: str | None = None
    tracks: list[ManifestTrack] = []
    collections: list[str] = []

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") or line.endswith("]"):
            if not (line.startswith("[") and line.endswith("]")):
                raise ManifestParseError(f"Line {line_number}: invalid section header.")
            section_name = line[1:-1].strip().lower()
            section = _MANIFEST_SECTIONS.get(section_name)
            if section is None:
                raise ManifestParseError(f"Line {line_number}: unknown section [{section_name}].")
            continue

        if section is None:
            raise ManifestParseError(f"Line {line_number}: link found before any section header.")

        if section == "tracks":
            spotify_url, youtube_url = _parse_manifest_track_line(line, line_number)
            source_type, _ = parse_spotify_url(spotify_url)
            if source_type != "track":
                raise ManifestParseError(f"Line {line_number}: expected a Spotify track URL.")
            tracks.append(ManifestTrack(spotify_url, youtube_url))
            continue

        if "|" in line:
            raise ManifestParseError(
                f"Line {line_number}: YouTube links are only supported in [tracks]."
            )
        source_type, _ = parse_spotify_url(line)
        if section == "playlists" and source_type != "playlist":
            raise ManifestParseError(f"Line {line_number}: expected a Spotify playlist URL.")
        if section == "albums" and source_type != "album":
            raise ManifestParseError(f"Line {line_number}: expected a Spotify album URL.")
        collections.append(line)

    if not tracks and not collections:
        raise ManifestParseError("Manifest does not contain any links.")

    return DownloadManifest(tracks=tracks, collections=collections)


def _parse_manifest_track_line(line: str, line_number: int) -> tuple[str, str | None]:
    spotify_url, separator, youtube_url = line.partition("|")
    spotify_url = spotify_url.strip()
    youtube_url = youtube_url.strip() if separator else None
    if not spotify_url:
        raise ManifestParseError(f"Line {line_number}: missing Spotify track URL.")
    if separator and not youtube_url:
        raise ManifestParseError(f"Line {line_number}: missing YouTube URL after '|'.")
    return spotify_url, youtube_url
