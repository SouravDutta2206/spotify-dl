from __future__ import annotations

from spotify_dl.cover_art import CoverResolver
from spotify_dl.source_cache import CoverCache
from tests.test_filesystem import make_track


def test_cover_resolver_returns_cached_cover_without_fetching(tmp_path, monkeypatch):
    cache = CoverCache(tmp_path)
    cache.put("album-id", b"cover", "image/png")
    resolver = CoverResolver(cache)
    track = make_track(album_id="album-id", album_art_url="https://example.com/cover.jpg")
    monkeypatch.setattr(
        "spotify_dl.cover_art.requests.get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not fetch")),
    )

    assert resolver.get_or_fetch(track) == (b"cover", "image/png")


def test_cover_resolver_fetches_and_caches_cover(tmp_path, monkeypatch):
    class Response:
        content = b"fresh-cover"
        headers = {"content-type": "image/webp; charset=utf-8"}

        def raise_for_status(self):
            return None

    cache = CoverCache(tmp_path)
    resolver = CoverResolver(cache)
    track = make_track(album_id="album-id", album_art_url="https://example.com/cover.webp")
    monkeypatch.setattr("spotify_dl.cover_art.requests.get", lambda url, timeout: Response())

    assert resolver.get_or_fetch(track) == (b"fresh-cover", "image/webp")
    assert cache.get("album-id") == (b"fresh-cover", "image/webp")


def test_cover_resolver_prefetch_fetches_each_album_once(tmp_path, monkeypatch):
    class Response:
        content = b"fresh-cover"
        headers = {"content-type": "image/jpeg"}

        def raise_for_status(self):
            return None

    calls = []
    cache = CoverCache(tmp_path)
    resolver = CoverResolver(cache)
    monkeypatch.setattr(
        "spotify_dl.cover_art.requests.get",
        lambda url, timeout: calls.append(url) or Response(),
    )

    resolver.prefetch(
        [
            make_track(album_id="album-id", album_art_url="https://example.com/cover.jpg"),
            make_track(album_id="album-id", album_art_url="https://example.com/cover.jpg"),
        ]
    )

    assert calls == ["https://example.com/cover.jpg"]
