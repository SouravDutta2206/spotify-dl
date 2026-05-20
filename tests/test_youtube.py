from __future__ import annotations

from spotify_dl.youtube import (
    YouTubeSearcher,
    build_yt_dlp_options,
    javascript_runtime_options,
    make_direct_match,
    parse_cookies_from_browser,
    parse_youtube_video_id,
)
from tests.conftest import make_track


def test_youtube_duration_and_text_score():
    track = make_track(title="Song", artists=["Artist"], duration_ms=180000)
    match = YouTubeSearcher()._score(
        {"id": "vid", "title": "Artist - Song audio", "duration": 181},
        track,
        "Artist - Song audio",
    )

    assert match.match_score >= 90
    assert match.youtube_url == "https://www.youtube.com/watch?v=vid"


def test_javascript_runtime_prefers_deno(monkeypatch):
    monkeypatch.setattr(
        "spotify_dl.youtube.shutil.which",
        lambda name: {"deno": "C:/deno.exe", "node": "C:/node.exe"}.get(name),
    )

    assert javascript_runtime_options() == {"deno": {"path": "C:/deno.exe"}}


def test_javascript_runtime_falls_back_to_node(monkeypatch):
    monkeypatch.setattr(
        "spotify_dl.youtube.shutil.which",
        lambda name: {"node": "C:/node.exe"}.get(name),
    )

    assert javascript_runtime_options() == {"node": {"path": "C:/node.exe"}}


def test_search_options_use_shared_defaults(monkeypatch):
    monkeypatch.setattr("spotify_dl.youtube.javascript_runtime_options", lambda: {})

    assert build_yt_dlp_options(mode="search", verbose=False) == {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
    }


def test_parse_cookies_from_browser_name_only():
    assert parse_cookies_from_browser("chrome") == ("chrome", None, None, None)


def test_parse_cookies_from_browser_with_profile_path():
    assert parse_cookies_from_browser(r"firefox:C:\Zen\Profiles\Default") == (
        "firefox",
        r"C:\Zen\Profiles\Default",
        None,
        None,
    )


def test_parse_cookies_from_browser_with_keyring_and_container():
    assert parse_cookies_from_browser("firefox+kwallet:default::personal") == (
        "firefox",
        "default",
        "kwallet",
        "personal",
    )


def test_parse_youtube_video_id_from_direct_links():
    assert parse_youtube_video_id("https://www.youtube.com/watch?v=abc123_DEF4") == "abc123_DEF4"
    assert parse_youtube_video_id("https://youtu.be/abc123_DEF4") == "abc123_DEF4"


def test_make_direct_match_uses_supplied_url():
    match = make_direct_match("https://www.youtube.com/watch?v=abc123_DEF4")

    assert match.youtube_url == "https://www.youtube.com/watch?v=abc123_DEF4"
    assert match.video_id == "abc123_DEF4"
    assert match.match_score == -1
