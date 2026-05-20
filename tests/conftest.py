from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from spotify_dl.models import AppConfig, TrackMetadata


def make_track(**overrides) -> TrackMetadata:
    data = {
        "spotify_id": "1",
        "isrc": None,
        "title": "A/B: Song?",
        "artists": ["Artist"],
        "track_number": 3,
        "disc_number": 1,
        "duration_ms": 180000,
        "album_id": "alb",
        "album_name": "Album",
        "album_artist": "Artist",
        "album_total_tracks": 10,
        "album_total_discs": 1,
        "album_release_date": "2020-01-01",
        "album_art_url": "",
        "album_genres": [],
    }
    data.update(overrides)
    return TrackMetadata(**data)


@pytest.fixture
def app_config(tmp_path) -> AppConfig:
    return AppConfig(
        spotify_client_id="id",
        spotify_client_secret="secret",
        spotify_user_access_token="access",
        spotify_user_refresh_token="refresh",
        spotify_user_token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
        output_directory=tmp_path,
        audio_quality="0",
        youtube_cookie_browser=None,
        youtube_cookie_file=None,
        auth_callback_port=8888,
        concurrency=3,
    )
