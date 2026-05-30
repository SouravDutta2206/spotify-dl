from __future__ import annotations

from unittest.mock import MagicMock

from spotify_dl.filesystem import FileSystem
from spotify_dl.models import PlaylistSummary
from spotify_dl.source_cache import SourceCache
from spotify_dl.sync import has_missing_track_files, run_sync
from tests.conftest import make_track

import pytest

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


def test_run_sync_skips_when_up_to_date(tmp_path, monkeypatch, app_config):
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

    config = app_config
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


def test_run_sync_downloads_on_snapshot_change(tmp_path, monkeypatch, app_config):
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

    config = app_config
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


def test_run_sync_downloads_when_files_missing(tmp_path, monkeypatch, app_config):
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

    config = app_config
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


def test_playlists_list_command(tmp_path, monkeypatch, capsys, app_config):
    config = app_config
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
        "spotify_dl.main.spotify_client_from_options",
        lambda options: (config, client),
    )

    monkeypatch.setattr("sys.argv", ["spotify-dl", "playlists", "list"])

    from spotify_dl.main import main
    main()

    captured = capsys.readouterr()
    assert "Test" in captured.out
    assert "5 tracks" in captured.out


def test_playlists_without_subcommand_shows_help(monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["spotify-dl", "playlists"])

    from spotify_dl.main import main
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "playlists" in captured.err
