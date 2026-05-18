from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from click.testing import CliRunner

from spotify_dl.filesystem import FileSystem
from spotify_dl.main import cli
from spotify_dl.models import AppConfig, PlaylistSummary
from spotify_dl.source_cache import SourceCache
from spotify_dl.sync import has_missing_track_files, run_sync
from tests.test_filesystem import make_track


def test_has_missing_track_files_detects_missing_primary(tmp_path):
    fs = FileSystem(tmp_path)
    track = make_track()

    assert has_missing_track_files(fs, [track], make_playlist=False, playlist_name="Playlist") is True


def test_has_missing_track_files_complete(tmp_path):
    fs = FileSystem(tmp_path)
    track = make_track()
    path = fs.get_track_path(track)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"mp3")

    assert has_missing_track_files(fs, [track], make_playlist=False, playlist_name="Playlist") is False


def test_has_missing_track_files_detects_missing_mirror(tmp_path):
    fs = FileSystem(tmp_path)
    track = make_track()
    path = fs.get_track_path(track)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"mp3")

    assert has_missing_track_files(fs, [track], make_playlist=True, playlist_name="Playlist") is True


def test_run_sync_skips_when_up_to_date(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache = SourceCache(cache_dir)
    track = make_track(spotify_id="track-id")
    cache.save(
        kind="playlist",
        source_id="playlist-id",
        source_name="Playlist",
        snapshot_id="snap",
        tracks=[track],
    )
    path = FileSystem(tmp_path).get_track_path(track)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"mp3")

    config = _config(tmp_path)
    client = MagicMock()
    client.source_cache = cache
    client.get_playlist_header.return_value = {"snapshot_id": "snap", "name": "Playlist"}
    download_calls = []
    monkeypatch.setattr(
        "spotify_dl.sync.spotify_client_from_options",
        lambda options: (config, client),
    )
    monkeypatch.setattr(
        "spotify_dl.sync.download_tracks",
        lambda **kwargs: download_calls.append(kwargs),
    )

    run_sync({})

    assert download_calls == []
    client.get_playlist.assert_not_called()


def test_run_sync_downloads_on_snapshot_change(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache = SourceCache(cache_dir)
    track = make_track(spotify_id="track-id")
    cache.save(
        kind="playlist",
        source_id="playlist-id",
        source_name="Playlist",
        snapshot_id="old-snap",
        tracks=[track],
    )

    config = _config(tmp_path)
    client = MagicMock()
    client.source_cache = cache
    client.get_playlist_header.return_value = {"snapshot_id": "new-snap", "name": "Playlist"}
    client.get_playlist.return_value = [track]
    download_calls = []
    monkeypatch.setattr(
        "spotify_dl.sync.spotify_client_from_options",
        lambda options: (config, client),
    )
    monkeypatch.setattr(
        "spotify_dl.sync.download_tracks",
        lambda **kwargs: download_calls.append(kwargs),
    )

    run_sync({})

    client.get_playlist.assert_called_once_with(
        "playlist-id",
        snapshot_id="new-snap",
        playlist_name="Playlist",
    )
    assert len(download_calls) == 1
    assert download_calls[0]["source_type"] == "playlist"
    assert download_calls[0]["source_name"] == "Playlist"
    assert download_calls[0]["tracks"] == [track]
    assert download_calls[0]["options"]["skip_existing"] is True


def test_run_sync_downloads_when_files_missing(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    cache = SourceCache(cache_dir)
    track = make_track(spotify_id="track-id")
    cache.save(
        kind="playlist",
        source_id="playlist-id",
        source_name="Playlist",
        snapshot_id="snap",
        tracks=[track],
    )

    config = _config(tmp_path)
    client = MagicMock()
    client.source_cache = cache
    client.get_playlist_header.return_value = {"snapshot_id": "snap", "name": "Playlist"}
    download_calls = []
    monkeypatch.setattr(
        "spotify_dl.sync.spotify_client_from_options",
        lambda options: (config, client),
    )
    monkeypatch.setattr(
        "spotify_dl.sync.download_tracks",
        lambda **kwargs: download_calls.append(kwargs),
    )

    run_sync({})

    client.get_playlist.assert_not_called()
    assert len(download_calls) == 1
    assert download_calls[0]["source_type"] == "playlist"
    assert download_calls[0]["source_name"] == "Playlist"
    assert download_calls[0]["tracks"] == [track]
    assert download_calls[0]["options"]["skip_existing"] is True


def test_playlists_list_command(tmp_path, monkeypatch):
    config = _config(tmp_path)
    client = MagicMock()
    client.list_user_playlists.return_value = [
        PlaylistSummary(
            playlist_id="id",
            name="Test",
            owner="Me",
            track_count=5,
            visibility="private",
            cover_art_url=None,
            spotify_url="https://open.spotify.com/playlist/id",
        )
    ]
    monkeypatch.setattr(
        "spotify_dl.commands.playlists.spotify_client_from_options",
        lambda options: (config, client),
    )

    result = CliRunner().invoke(cli, ["playlists", "list"])

    assert result.exit_code == 0
    assert "Test" in result.output
    assert "5 tracks" in result.output


def test_playlists_without_subcommand_shows_help():
    result = CliRunner().invoke(cli, ["playlists"])

    assert result.exit_code == 2
    assert "list" in result.output
    assert "sync" in result.output


def _config(tmp_path) -> AppConfig:
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
