from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal


@dataclass(slots=True)
class AppConfig:
    spotify_client_id: str
    spotify_client_secret: str
    spotify_user_access_token: str | None
    spotify_user_refresh_token: str | None
    spotify_user_token_expiry: datetime | None
    output_directory: Path
    audio_quality: str
    youtube_cookie_browser: str | None
    youtube_cookie_file: Path | None
    auth_callback_port: int
    concurrency: int


@dataclass(slots=True)
class TrackMetadata:
    spotify_id: str
    isrc: str | None
    title: str
    artists: list[str]
    track_number: int
    disc_number: int
    duration_ms: int
    album_id: str
    album_name: str
    album_artist: str
    album_total_tracks: int
    album_total_discs: int
    album_release_date: str
    album_art_url: str
    album_genres: list[str]


@dataclass(slots=True)
class PlaylistSummary:
    playlist_id: str
    name: str
    owner: str
    track_count: int
    visibility: Literal["public", "private", "collaborative"]
    cover_art_url: str | None
    spotify_url: str


@dataclass(slots=True)
class AccountProfile:
    display_name: str
    spotify_user_id: str
    account_type: str
    account_id: str
    country: str
    email: str
    followers: int
    explicit_filter_enabled: bool


@dataclass(slots=True)
class YouTubeMatch:
    youtube_url: str
    video_id: str
    video_title: str
    duration_seconds: int
    match_score: int
    search_query: str


@dataclass(slots=True)
class DownloadResult:
    track: TrackMetadata
    match: YouTubeMatch | None
    final_mp3_path: Path | None
    status: Literal["done", "skipped", "failed"]
    error: str | None
