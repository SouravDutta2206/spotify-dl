from __future__ import annotations

from spotify_dl.filesystem import FileSystem, sanitize_component
from spotify_dl.models import TrackMetadata


def make_track(**overrides):
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


def test_sanitize_component():
    assert sanitize_component(' A/B: C* ') == "A_B_ C_"


def test_track_path(tmp_path):
    fs = FileSystem(tmp_path)
    assert fs.get_track_path(make_track()) == tmp_path / "Artists" / "Artist" / "Album (2020)" / "03 - A_B_ Song_.mp3"


def test_multidisc_filename(tmp_path):
    fs = FileSystem(tmp_path)
    track = make_track(disc_number=2, album_total_discs=2, track_number=1)
    assert fs.get_track_filename(track).startswith("2-01 - ")


def test_playlist_mirror_path(tmp_path):
    fs = FileSystem(tmp_path)
    track = make_track(title="A/B: Song?")
    assert fs.get_playlist_mirror_path(track, "My Playlist") == (
        tmp_path / "My Playlist" / "A_B_ Song_.mp3"
    )

