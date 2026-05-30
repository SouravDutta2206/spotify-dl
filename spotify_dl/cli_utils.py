from __future__ import annotations

from typing import Any

from spotify_dl.config import ConfigManager
from spotify_dl.models import AppConfig
from spotify_dl.spotify import SpotifyClient

_DOWNLOAD_DEFAULTS: dict[str, Any] = {
    "skip_existing": True,
    "dry_run": False,
    "verbose": False,
    "youtube_link": None,
    "make_playlist": False,
}


def normalize_download_options(
    options: dict[str, Any],
    *,
    force_skip_existing: bool | None = None,
) -> dict[str, Any]:
    normalized = {**_DOWNLOAD_DEFAULTS, **{key: value for key, value in options.items() if value is not None}}
    if force_skip_existing is not None:
        normalized["skip_existing"] = force_skip_existing
    return normalized


def config_from_options(
    options: dict[str, Any],
    manager: ConfigManager | None = None,
) -> tuple[AppConfig, ConfigManager]:
    mgr = manager or ConfigManager()
    config = mgr.load(
        client_id=options.get("client_id"),
        client_secret=options.get("client_secret"),
        output_directory=options.get("output") or options.get("output_directory"),
        quality=options.get("quality"),
        youtube_cookie_browser=options.get("youtube_cookies_from") or options.get("youtube_cookie_browser"),
        youtube_cookie_file=options.get("youtube_cookie_file"),
        concurrency=options.get("concurrency"),
    )
    return config, mgr


def spotify_client_from_options(
    options: dict[str, Any],
    manager: ConfigManager | None = None,
) -> tuple[AppConfig, SpotifyClient]:
    config, mgr = config_from_options(options, manager)
    return config, SpotifyClient(config, mgr)
