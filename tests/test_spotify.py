from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from spotify_dl.config import ConfigManager
from spotify_dl.spotify import SpotifyClient
from spotify_dl.spotify import (
    _iter_page_items,
    _playlist_track_count,
    parse_spotify_url,
    track_from_spotify,
)
from tests.conftest import make_track_payload


def test_parse_spotify_url():
    assert parse_spotify_url("https://open.spotify.com/album/abc123?si=x") == ("album", "abc123")
    assert parse_spotify_url("spotify:track:def456") == ("track", "def456")


def test_parse_spotify_url_rejects_invalid():
    assert parse_spotify_url("https://example.com/nope") == (None, None)


def test_track_from_spotify_maps_metadata():
    track = track_from_spotify(
        {
            "id": "track-id",
            "external_ids": {"isrc": "ISRC"},
            "name": "Song",
            "artists": [{"name": "A"}, {"name": "B"}],
            "track_number": 2,
            "disc_number": 1,
            "duration_ms": 123000,
            "album": {
                "id": "album-id",
                "name": "Album",
                "artists": [{"name": "Album Artist"}],
                "total_tracks": 9,
                "release_date": "2024-01-01",
                "images": [{"url": "small", "height": 64}, {"url": "large", "height": 640}],
                "genres": ["pop"],
            },
        }
    )

    assert track.spotify_id == "track-id"
    assert track.artists == ["A", "B"]
    assert track.album_art_url == "large"
    assert track.album_artist == "Album Artist"


def test_user_client_refreshes_expired_token(app_config, tmp_path, monkeypatch):
    manager = ConfigManager(tmp_path / "config.json")
    config = replace(
        app_config,
        spotify_user_access_token="old-access",
        spotify_user_token_expiry=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    class FakeOAuth:
        def __init__(self, **kwargs):
            pass

        def refresh_access_token(self, refresh_token):
            assert refresh_token == "refresh"
            return {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "expires_at": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            }

    monkeypatch.setattr("spotify_dl.auth.SpotifyOAuth", FakeOAuth)

    SpotifyClient(config, manager)._user_client()

    assert config.spotify_user_access_token == "new-access"
    assert manager.read_raw()["spotify"]["user_auth"]["access_token"] == "new-access"


def test_playlist_track_count_from_summary():
    assert _playlist_track_count({"tracks": {"total": 42}}) == 42


def test_get_current_user_profile_maps_account_fields(app_config, tmp_path):
    class FakeUserClient:
        def current_user(self):
            return {
                "account_id": "R6621MQqcn",
                "country": "IN",
                "display_name": "LOL",
                "email": "user@example.com",
                "explicit_content": {"filter_enabled": False, "filter_locked": False},
                "followers": {"href": None, "total": 7},
                "id": "spotify-user-id",
                "product": "premium",
            }

    client = SpotifyClient(app_config, cache_dir=tmp_path / "cache")
    client._user_client = lambda: FakeUserClient()  # type: ignore[method-assign]

    profile = client.get_current_user_profile()

    assert profile.display_name == "LOL"
    assert profile.spotify_user_id == "spotify-user-id"
    assert profile.account_type == "premium"
    assert profile.account_id == "R6621MQqcn"
    assert profile.country == "IN"
    assert profile.email == "user@example.com"
    assert profile.followers == 7
    assert profile.explicit_filter_enabled is False


def test_iter_page_items_follows_spotify_next_pages():
    pages = [
        {"items": [{"id": "first"}], "next": "next-page"},
        {"items": [{"id": "second"}], "next": None},
    ]

    class FakeClient:
        def next(self, page):
            assert page is pages[0]
            return pages[1]

    assert list(_iter_page_items(FakeClient(), pages[0])) == [{"id": "first"}, {"id": "second"}]


def test_list_user_playlists_falls_back_when_summary_count_is_zero(app_config, tmp_path, monkeypatch):
    class FakeUserClient:
        def current_user_playlists(self, limit):
            return {
                "items": [
                    {
                        "id": "playlist-id",
                        "name": "Playlist",
                        "owner": {"display_name": "Owner"},
                        "tracks": {"total": 0},
                        "public": True,
                        "collaborative": False,
                        "images": [],
                        "external_urls": {"spotify": "https://open.spotify.com/playlist/playlist-id"},
                    }
                ],
                "next": None,
            }

    monkeypatch.setattr("spotify_dl.spotify.spotipy.Spotify", lambda *args, **kwargs: FakeUserClient())
    client = SpotifyClient(app_config, cache_dir=tmp_path / "cache")
    monkeypatch.setattr(client, "get_playlist_track_count", lambda playlist_id: 23)

    playlists = client.list_user_playlists()

    assert playlists[0].track_count == 23


def test_get_playlist_track_count_uses_playlist_items_total(app_config, tmp_path):
    class FakeUserClient:
        def playlist_items(self, playlist_id, limit, offset, fields):
            assert playlist_id == "playlist-id"
            assert limit == 1
            assert offset == 0
            assert fields == "total"
            return {"total": 77}

    client = SpotifyClient(app_config, cache_dir=tmp_path / "cache")
    client._user_client = lambda: FakeUserClient()  # type: ignore[method-assign]

    assert client.get_playlist_track_count("playlist-id") == 77


def test_get_playlist_uses_user_client_when_logged_in(app_config, tmp_path):
    class FakeUserClient:
        used = False

        def playlist(self, playlist_id, fields):
            return {"id": playlist_id, "name": "Playlist", "snapshot_id": "snap"}

        def playlist_items(self, playlist_id, limit, offset):
            self.used = True
            return {
                "items": [{"track": make_track_payload("track-id")}],
                "next": None,
            }

        def tracks(self, track_ids):
            return {"tracks": [make_track_payload(track_ids[0])]}

    user_client = FakeUserClient()
    client = SpotifyClient(app_config, cache_dir=tmp_path / "cache")
    client._user_client = lambda: user_client  # type: ignore[method-assign]
    tracks = client.get_playlist("playlist-id")

    assert user_client.used
    assert tracks[0].spotify_id == "track-id"


def test_get_playlist_accepts_spotify_item_shape(app_config, tmp_path):
    class FakeUserClient:
        def playlist(self, playlist_id, fields):
            return {"id": playlist_id, "name": "Playlist", "snapshot_id": "snap"}

        def playlist_items(self, playlist_id, limit, offset):
            return {"items": [{"item": make_track_payload("track-id")}], "next": None}

        def tracks(self, track_ids):
            return {"tracks": [make_track_payload(track_ids[0])]}

    client = SpotifyClient(app_config, cache_dir=tmp_path / "cache")
    client._user_client = lambda: FakeUserClient()  # type: ignore[method-assign]

    assert client.get_playlist("playlist-id")[0].spotify_id == "track-id"


def test_get_playlist_uses_cache_when_snapshot_unchanged(app_config, tmp_path):
    client = SpotifyClient(app_config, cache_dir=tmp_path / "cache")
    client.source_cache.write_collection(
        "playlist",
        "playlist-id",
        "Playlist",
        [track_from_spotify(make_track_payload("track-id"))],
        snapshot_id="snap",
    )

    class FakeUserClient:
        def playlist_items(self, playlist_id, limit, offset):
            raise AssertionError("playlist items should not be fetched when snapshot is unchanged")

    client._user_client = lambda: FakeUserClient()  # type: ignore[method-assign]

    tracks = client.get_playlist("playlist-id", snapshot_id="snap", playlist_name="Playlist")

    assert tracks[0].spotify_id == "track-id"


def test_get_album_uses_cache(app_config, tmp_path):
    config = replace(
        app_config,
        spotify_user_access_token=None,
        spotify_user_refresh_token=None,
        spotify_user_token_expiry=None,
    )
    client = SpotifyClient(config, cache_dir=tmp_path / "cache")
    client.source_cache.write_collection(
        "album",
        "album-id",
        "Album",
        [track_from_spotify(make_track_payload("track-id"))],
    )
    client.client.album = lambda album_id: (_ for _ in ()).throw(
        AssertionError("album should not be fetched when cached")
    )

    assert client.get_album("album-id")[0].spotify_id == "track-id"


def test_get_track_uses_cache_and_updates_youtube_link(app_config, tmp_path):
    client = SpotifyClient(app_config, cache_dir=tmp_path / "cache")
    client.source_cache.write_track(track_from_spotify(make_track_payload("track-id")))
    client.client.track = lambda track_id: (_ for _ in ()).throw(
        AssertionError("track should not be fetched when cached")
    )

    track = client.get_track("track-id", youtube_link="https://youtube.com/watch?v=abc")

    assert track.spotify_id == "track-id"
    cached = client.source_cache.read_track("track-id")
    assert cached is not None and cached[1] == "https://youtube.com/watch?v=abc"


def test_get_tracks_batches_spotify_requests(app_config, tmp_path):
    config = replace(
        app_config,
        spotify_user_access_token=None,
        spotify_user_refresh_token=None,
        spotify_user_token_expiry=None,
        concurrency=5,
    )
    calls = []
    client = SpotifyClient(config, cache_dir=tmp_path / "cache")

    def fake_tracks(track_ids):
        calls.append(track_ids)
        return {"tracks": [make_track_payload(track_id) for track_id in track_ids]}

    client.client.tracks = fake_tracks

    tracks = client.get_tracks([str(index) for index in range(120)])

    assert len(tracks) == 120
    assert [len(call) for call in calls] == [50, 50, 20]
