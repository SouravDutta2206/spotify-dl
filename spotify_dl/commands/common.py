from __future__ import annotations

from collections.abc import Callable
from functools import reduce
from typing import Any, TypeVar

import click

from spotify_dl.config import ConfigManager
from spotify_dl.exceptions import SpotifyDlError
from spotify_dl.models import AppConfig
from spotify_dl.spotify import SpotifyClient

F = TypeVar("F", bound=Callable[..., Any])


def config_manager() -> ConfigManager:
    return ConfigManager()


def load_config(**overrides):
    return config_manager().load(**overrides)


def handle_spotify_dl_error(exc: SpotifyDlError) -> click.ClickException:
    return click.ClickException(str(exc))


def output_directory_option(f: F) -> F:
    return click.option(
        "--output",
        "-o",
        "output_directory",
        help="Set the output directory for downloaded files.",
    )(f)


def quality_option(f: F) -> F:
    return click.option(
        "--quality",
        "-q",
        type=click.Choice(["0", "128", "192", "320"]),
        help="Set the audio quality (e.g. 128, 192, 320).",
    )(f)


def client_id_option(f: F) -> F:
    return click.option("--client-id", help="Spotify API client ID.")(f)


def client_secret_option(f: F) -> F:
    return click.option("--client-secret", help="Spotify API client secret.")(f)


def youtube_cookie_browser_option(f: F) -> F:
    return click.option(
        "--youtube-cookies-from",
        "youtube_cookie_browser",
        help="Browser to extract YouTube cookies from.",
    )(f)


def youtube_cookie_file_option(f: F) -> F:
    return click.option(
        "--youtube-cookie-file",
        "youtube_cookie_file",
        help="Path to a cookies.txt file for YouTube.",
    )(f)


def dry_run_option(f: F) -> F:
    return click.option(
        "--dry-run",
        is_flag=True,
        default=None,
        help="Simulate the download process without fetching files.",
    )(f)


def verbose_option(f: F) -> F:
    return click.option("--verbose", "-v", is_flag=True, default=None, help="Enable verbose output.")(f)


def concurrency_option(f: F) -> F:
    return click.option(
        "--concurrency",
        "-c",
        type=int,
        help="Maximum number of concurrent downloads.",
    )(f)


def auth_callback_port_option(f: F) -> F:
    return click.option(
        "--auth-port",
        "auth_callback_port",
        type=int,
        help="Port to use for the local authentication callback server.",
    )(f)


def make_playlist_option(f: F) -> F:
    return click.option(
        "--make-playlist",
        is_flag=True,
        default=None,
        help="Create a local folder mirroring the Spotify playlist.",
    )(f)


def skip_existing_root_option(f: F) -> F:
    return click.option(
        "--skip-existing/--no-skip-existing",
        default=True,
        help="Skip downloading files that already exist.",
    )(f)


def skip_existing_command_option(f: F) -> F:
    return click.option(
        "--skip-existing/--no-skip-existing",
        default=None,
        help="Skip downloading files that already exist.",
    )(f)


def youtube_link_option(f: F) -> F:
    return click.option(
        "--youtube-link",
        "youtube_link",
        default=None,
        help="Use this YouTube URL instead of searching.",
    )(f)


_CORE_DOWNLOAD_OPTIONS: tuple[Callable[[Any], Any], ...] = (
    output_directory_option,
    quality_option,
    client_id_option,
    client_secret_option,
    youtube_cookie_browser_option,
    youtube_cookie_file_option,
    dry_run_option,
    verbose_option,
    concurrency_option,
    make_playlist_option,
)


def _apply_options(function: F, options: tuple[Callable[[Any], Any], ...]) -> F:
    return reduce(lambda fn, option: option(fn), reversed(options), function)  # type: ignore[arg-type]


def root_cli_options(f: F) -> F:
    """Options for the root CLI group (global defaults)."""
    return _apply_options(
        f,
        _CORE_DOWNLOAD_OPTIONS
        + (skip_existing_root_option, youtube_link_option),
    )


def download_command_options(f: F) -> F:
    """Per-command overrides for the hidden download command."""
    return _apply_options(
        f,
        _CORE_DOWNLOAD_OPTIONS
        + (skip_existing_command_option, youtube_link_option),
    )


def sync_command_options(f: F) -> F:
    """Options for playlists sync (inherits skip-existing from normalize)."""
    return _apply_options(f, _CORE_DOWNLOAD_OPTIONS)


_CONFIG_PERSIST_OPTIONS: tuple[Callable[[Any], Any], ...] = (
    client_id_option,
    client_secret_option,
    output_directory_option,
    quality_option,
    youtube_cookie_browser_option,
    youtube_cookie_file_option,
    concurrency_option,
    auth_callback_port_option,
)


def config_set_command_options(f: F) -> F:
    """Options for config set (persisted settings only)."""
    return _apply_options(f, _CONFIG_PERSIST_OPTIONS)


def options_to_config_partial(options: dict[str, Any]) -> dict[str, Any]:
    """Map merged CLI options to a ConfigManager.save() partial payload."""
    partial: dict[str, Any] = {}
    spotify: dict[str, Any] = {}
    output: dict[str, Any] = {}
    youtube: dict[str, Any] = {}
    auth: dict[str, Any] = {}
    if options.get("client_id"):
        spotify["client_id"] = options["client_id"]
    if options.get("client_secret"):
        spotify["client_secret"] = options["client_secret"]
    if options.get("output_directory"):
        output["directory"] = options["output_directory"]
    if options.get("quality"):
        output["quality"] = options["quality"]
    if options.get("youtube_cookie_browser"):
        youtube["cookie_browser"] = options["youtube_cookie_browser"]
    if options.get("youtube_cookie_file"):
        youtube["cookie_file"] = options["youtube_cookie_file"]
    if options.get("auth_callback_port") is not None:
        auth["callback_port"] = options["auth_callback_port"]
    if options.get("concurrency") is not None:
        partial["concurrency"] = options["concurrency"]
    if spotify:
        partial["spotify"] = spotify
    if output:
        partial["output"] = output
    if youtube:
        partial["youtube"] = youtube
    if auth:
        partial["auth"] = auth
    return partial


def merge_cli_options(ctx: click.Context, **command_kwargs: Any) -> dict[str, Any]:
    """Merge params from root → … → current command; explicit command kwargs win."""
    layers: list[dict[str, Any]] = []
    node: click.Context | None = ctx
    while node is not None:
        if node.params:
            layers.append(node.params)
        node = node.parent
    merged: dict[str, Any] = {}
    for layer in reversed(layers):
        merged.update(layer)
    merged.update({key: value for key, value in command_kwargs.items() if value is not None})
    return merged


def normalize_download_options(
    options: dict[str, Any],
    *,
    force_skip_existing: bool | None = None,
) -> dict[str, Any]:
    normalized = dict(options)
    if force_skip_existing is not None:
        normalized["skip_existing"] = force_skip_existing
    else:
        normalized.setdefault("skip_existing", True)
    normalized.setdefault("dry_run", False)
    normalized.setdefault("verbose", False)
    normalized.setdefault("youtube_link", None)
    normalized.setdefault("make_playlist", False)
    return normalized


def config_from_options(options: dict[str, Any]) -> AppConfig:
    return load_config(
        client_id=options.get("client_id"),
        client_secret=options.get("client_secret"),
        output_directory=options.get("output_directory"),
        quality=options.get("quality"),
        youtube_cookie_browser=options.get("youtube_cookie_browser"),
        youtube_cookie_file=options.get("youtube_cookie_file"),
        concurrency=options.get("concurrency"),
    )


def spotify_client_from_options(options: dict[str, Any]) -> tuple[AppConfig, SpotifyClient]:
    config = config_from_options(options)
    return config, SpotifyClient(config, config_manager())
