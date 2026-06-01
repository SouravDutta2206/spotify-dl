from __future__ import annotations

from spotify_dl.source_cache import SourceCache
from tests.conftest import make_track


def test_playlist_cache_requires_matching_snapshot(tmp_path):
    cache = SourceCache(tmp_path)
    track = make_track(spotify_id="track-id")

    cache.write_collection(
        "playlist",
        "playlist-id",
        "Playlist",
        [track],
        snapshot_id="snap-1",
    )

    cached = cache.read_collection("playlist", "playlist-id")
    assert cached is not None
    assert cached["snapshot_id"] == "snap-1"
    assert cached["source_name"] == "Playlist"
    assert cached["tracks"][0]["spotify_id"] == "track-id"


def test_album_cache_does_not_need_snapshot(tmp_path):
    cache = SourceCache(tmp_path)
    track = make_track(spotify_id="track-id")

    cache.write_collection("album", "album-id", "Album", [track])

    cached = cache.read_collection("album", "album-id")
    assert cached is not None
    assert cached["tracks"][0]["album_name"] == "Album"


def test_iter_playlists_ignores_non_playlist_files(tmp_path):
    cache = SourceCache(tmp_path)
    track = make_track(spotify_id="track-id")
    cache.write_collection(
        "playlist",
        "abc123",
        "My Playlist",
        [track],
        snapshot_id="snap-1",
    )
    cache.write_collection("album", "album-id", "Album", [track])
    (tmp_path / "covers").mkdir()
    (tmp_path / "covers" / "ignored.json").write_text("{}", encoding="utf-8")
    (tmp_path / "playlist-.json").write_text("{}", encoding="utf-8")

    entries = list(cache.iter_playlists())

    assert entries == [("abc123", tmp_path / "playlist-abc123.json")]


def test_read_collection_rejects_wrong_kind(tmp_path):
    cache = SourceCache(tmp_path)
    track = make_track(spotify_id="track-id")
    cache.write_collection(
        "playlist",
        "playlist-id",
        "Playlist",
        [track],
        snapshot_id="snap-1",
    )

    payload = cache.read_collection("playlist", "playlist-id")

    assert payload is not None
    assert payload["snapshot_id"] == "snap-1"
    assert payload["source_name"] == "Playlist"
    assert cache.read_collection("album", "playlist-id") is None


def test_tracks_cache_stores_track_metadata_and_youtube_link(tmp_path):
    cache = SourceCache(tmp_path)
    track = make_track(spotify_id="track-id")

    cache.write_track(track, youtube_link="https://youtube.com/watch?v=abc")

    cached = cache.read_track("track-id")
    assert cached is not None
    cached_track, youtube_link = cached
    assert cached_track.spotify_id == "track-id"
    assert youtube_link == "https://youtube.com/watch?v=abc"


def test_tracks_cache_preserves_existing_youtube_link_when_updating_metadata(tmp_path):
    cache = SourceCache(tmp_path)
    cache.write_track(make_track(spotify_id="track-id"), youtube_link="https://youtube.com/watch?v=abc")

    cache.write_track(make_track(spotify_id="track-id", title="New Title"))

    cached = cache.read_track("track-id")
    assert cached is not None
    cached_track, youtube_link = cached
    assert cached_track.title == "New Title"
    assert youtube_link == "https://youtube.com/watch?v=abc"
