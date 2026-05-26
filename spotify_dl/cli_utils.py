from __future__ import annotations

from typing import Any

from spotify_dl.config import ConfigManager
from spotify_dl.models import AppConfig
from spotify_dl.spotify import SpotifyClient


def normalize_download_options(
    options: dict[str, Any],
    *,
    force_skip_existing: bool | None = None,
) -> dict[str, Any]:
    normalized = dict(options)
    if force_skip_existing is not None:
        normalized["skip_existing"] = force_skip_existing
    elif normalized.get("skip_existing") is None:
        normalized["skip_existing"] = True

    if normalized.get("dry_run") is None:
        normalized["dry_run"] = False

    if normalized.get("verbose") is None:
        normalized["verbose"] = False

    if normalized.get("youtube_link") is None:
        normalized["youtube_link"] = None

    if normalized.get("make_playlist") is None:
        normalized["make_playlist"] = False

    return normalized


def config_from_options(options: dict[str, Any]) -> AppConfig:
    return ConfigManager().load(
        client_id=options.get("client_id"),
        client_secret=options.get("client_secret"),
        output_directory=options.get("output") or options.get("output_directory"),
        quality=options.get("quality"),
        youtube_cookie_browser=options.get("youtube_cookies_from") or options.get("youtube_cookie_browser"),
        youtube_cookie_file=options.get("youtube_cookie_file"),
        concurrency=options.get("concurrency"),
    )


def spotify_client_from_options(options: dict[str, Any]) -> tuple[AppConfig, SpotifyClient]:
    config = config_from_options(options)
    return config, SpotifyClient(config, ConfigManager())
