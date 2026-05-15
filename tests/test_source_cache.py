from __future__ import annotations

from spotify_dl.source_cache import SourceCache
from tests.test_filesystem import make_track


def test_playlist_cache_requires_matching_snapshot(tmp_path):
    cache = SourceCache(tmp_path)
    track = make_track(spotify_id="track-id")

    cache.save(
        kind="playlist",
        source_id="playlist-id",
        source_name="Playlist",
        snapshot_id="snap-1",
        tracks=[track],
    )

    assert cache.load(kind="playlist", source_id="playlist-id", snapshot_id="snap-2") is None
    cached = cache.load(kind="playlist", source_id="playlist-id", snapshot_id="snap-1")
    assert cached is not None
    assert cached[0] == "Playlist"
    assert cached[1][0].spotify_id == "track-id"


def test_album_cache_does_not_need_snapshot(tmp_path):
    cache = SourceCache(tmp_path)
    track = make_track(spotify_id="track-id")

    cache.save(kind="album", source_id="album-id", source_name="Album", tracks=[track])

    cached = cache.load(kind="album", source_id="album-id")
    assert cached is not None
    assert cached[1][0].album_name == "Album"

