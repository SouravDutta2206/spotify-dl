from __future__ import annotations

from spotify_dl.downloader import parse_cookies_from_browser


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
