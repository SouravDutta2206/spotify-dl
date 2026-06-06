from __future__ import annotations

import argparse
from typing import Any

from spotify_dl.config import VALID_QUALITIES, ConfigManager
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


_CONFIG_KEY_MAP: dict[str, tuple[str, ...]] = {
    "client-id": ("spotify", "client_id"),
    "client-secret": ("spotify", "client_secret"),
    "output": ("output", "directory"),
    "quality": ("output", "quality"),
    "youtube-cookies-from": ("youtube", "cookie_browser"),
    "youtube-cookie-browser": ("youtube", "cookie_browser"),
    "youtube-cookie-file": ("youtube", "cookie_file"),
    "concurrency": ("concurrency",),
    "auth-port": ("auth", "callback_port"),
    "auth-callback-port": ("auth", "callback_port"),
}

_CONFIG_VALIDATORS: dict[str, tuple[set[str] | None, type | None, str]] = {
    "quality": (VALID_QUALITIES, None, "Audio quality must be one of: 0, 128, 192, 320"),
    "concurrency": (None, int, "Concurrency must be an integer."),
    "auth-port": (None, int, "Auth port must be an integer."),
    "auth-callback-port": (None, int, "Auth port must be an integer."),
}


# ─────────────────────────────────────────────────────────────────────────────
# Shared options (playlists sync + download)
# ─────────────────────────────────────────────────────────────────────────────

def add_shared_options(parser: argparse.ArgumentParser) -> None:
    grp = parser.add_argument_group("output options")
    grp.add_argument(
        "--output", "-o",
        metavar="DIR",
        default=None,
        help="Directory to save downloaded files.",
    )
    grp.add_argument(
        "--quality", "-q",
        metavar="QUALITY",
        choices=["0", "128", "192", "320"],
        default=None,
        help="Audio quality. Choices: 0 | 128 | 192 | 320.",
    )
    grp.add_argument(
        "--make-playlist",
        action="store_true",
        default=None,
        help="Mirror the playlist/album as a local sub-folder of tracks.",
    )
    grp.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Skip tracks that already exist locally. (default: enabled)",
    )
    grp.add_argument(
        "--concurrency", "-c",
        metavar="N",
        type=int,
        default=None,
        help="Number of concurrent download workers.",
    )
    grp.add_argument(
        "--dry-run",
        action="store_true",
        default=None,
        help="Simulate the operation without downloading anything.",
    )

    auth_grp = parser.add_argument_group("auth / api options")
    auth_grp.add_argument(
        "--client-id",
        metavar="ID",
        help="Spotify API client ID. Overrides stored auth for this run.",
    )
    auth_grp.add_argument(
        "--client-secret",
        metavar="SECRET",
        help="Spotify API client secret. Overrides stored auth for this run.",
    )
    auth_grp.add_argument(
        "--auth-port",
        metavar="PORT",
        type=int,
        default=None,
        help="Port for the Spotify OAuth callback server.",
    )

    yt_grp = parser.add_argument_group("youtube / cookies options")
    cookie_src = yt_grp.add_mutually_exclusive_group()
    cookie_src.add_argument(
        "--youtube-cookies-from",
        metavar="BROWSER",
        choices=["brave", "chrome", "chromium", "edge", "firefox", "opera", "safari", "vivaldi", "whale"],
        help="Extract YouTube cookies directly from a browser.",
    )
    cookie_src.add_argument(
        "--youtube-cookie-file",
        metavar="FILE",
        help="Path to an exported Netscape cookies.txt file for YouTube.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# auth
# ─────────────────────────────────────────────────────────────────────────────

def build_auth_parser(subparsers) -> None:
    auth_parser = subparsers.add_parser(
        "auth",
        help="Manage Spotify API authentication.",
        description=(
            "Authenticate with Spotify, remove stored credentials, or check "
            "the current login status.\n\n"
            "Examples:\n"
            "  spotify-dl auth login\n"
            "  spotify-dl auth status\n"
            "  spotify-dl auth logout"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    auth_sub = auth_parser.add_subparsers(dest="auth_command", metavar="COMMAND")
    auth_sub.required = True

    # login
    auth_sub.add_parser(
        "login",
        help="Authenticate with Spotify via OAuth.",
        description=(
            "Opens a browser window to complete OAuth authentication with Spotify.\n"
            "Credentials are stored securely for future use."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # logout
    auth_sub.add_parser(
        "logout",
        help="Remove stored Spotify credentials.",
        description="Deletes all locally stored Spotify tokens and credentials.",
    )

    # status
    auth_sub.add_parser(
        "status",
        help="Show the current authentication status.",
        description=(
            "Displays whether you are currently authenticated and which "
            "Spotify account is active."
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# config
# ─────────────────────────────────────────────────────────────────────────────

def build_config_parser(subparsers) -> None:
    config_parser = subparsers.add_parser(
        "config",
        help="Manage spotify-dl configuration.",
        description=(
            "View or modify persistent configuration values.\n\n"
            "Examples:\n"
            "  spotify-dl config show\n"
            "  spotify-dl config set output ~/Music\n"
            "  spotify-dl config set quality 320\n"
            "  spotify-dl config clear\n"
            "  spotify-dl config clear-cookies"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    config_sub = config_parser.add_subparsers(dest="config_command", metavar="COMMAND")
    config_sub.required = True

    # set
    set_parser = config_sub.add_parser(
        "set",
        help="Persist a configuration value.",
        description=(
            "Set a persistent configuration key-value pair.\n\n"
            "Configurable keys:\n"
            "  output, quality, concurrency, auth-port,\n"
            "  client-id, client-secret, youtube-cookies-from, youtube-cookie-file\n\n"
            "Example:\n"
            "  spotify-dl config set output ~/Music\n"
            "  spotify-dl config set quality 320"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    set_parser.add_argument("key",   metavar="KEY",   help="Configuration key to set.")
    set_parser.add_argument("value", metavar="VALUE", help="Value to assign.")

    # show
    config_sub.add_parser(
        "show",
        help="Display all current configuration values.",
        description="Prints every configuration key alongside its current value.",
    )

    # clear
    config_sub.add_parser(
        "clear",
        help="Reset all configuration to defaults.",
        description=(
            "Removes all user-defined configuration values and restores defaults.\n"
            "This does NOT affect stored auth credentials — use `auth logout` for that."
        ),
    )

    # clear-cookies
    config_sub.add_parser(
        "clear-cookies",
        help="Delete cached YouTube cookies.",
        description="Removes any YouTube cookies that were stored locally.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# playlists
# ─────────────────────────────────────────────────────────────────────────────

def build_profile_parser(subparsers) -> None:
    subparsers.add_parser(
        "profile",
        help="Show basic Spotify account information.",
        description=(
            "Fetches and displays basic account information for the logged-in "
            "Spotify user.\nRequires authentication — run `spotify-dl auth login` first."
        ),
    )


def build_playlists_parser(subparsers) -> None:
    pl_parser = subparsers.add_parser(
        "playlists",
        help="List or sync your Spotify playlists.",
        description=(
            "Interact with your Spotify library playlists.\n\n"
            "Examples:\n"
            "  spotify-dl playlists list\n"
            "  spotify-dl playlists sync\n"
            "  spotify-dl playlists sync --output ~/Music --quality 320 --dry-run"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    pl_sub = pl_parser.add_subparsers(dest="playlists_command", metavar="COMMAND")
    pl_sub.required = True

    # list
    pl_sub.add_parser(
        "list",
        help="List all playlists in your Spotify library.",
        description=(
            "Fetches and displays all playlists saved to your Spotify account.\n"
            "Requires authentication — run `spotify-dl auth login` first."
        ),
    )

    # sync
    sync_parser = pl_sub.add_parser(
        "sync",
        help="Sync all library playlists to local storage.",
        description=(
            "Downloads every track across all your playlists that is not already "
            "present locally.\n\n"
            "Example:\n"
            "  spotify-dl playlists sync --output ~/Music --quality 320 --concurrency 8"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_shared_options(sync_parser)


# ─────────────────────────────────────────────────────────────────────────────
# download
# ─────────────────────────────────────────────────────────────────────────────

def build_download_parser(subparsers) -> None:
    dl_parser = subparsers.add_parser(
        "download",
        help="Download tracks, albums, or playlists by Spotify URL.",
        description=(
            "Download one or more Spotify URLs (tracks, albums, or playlists).\n\n"
            "You may optionally pair each Spotify URL with a YouTube URL via\n"
            "--youtube-link to skip the search step. Use '_' as a placeholder\n"
            "to fall back to YouTube search for that position. When --youtube-link\n"
            "is used, its count must exactly match the number of Spotify track\n"
            "URLs given. Albums and playlists are not supported with --youtube-link.\n\n"
            "You can also load an INI-style link manifest with --from-file.\n\n"
            "Use 'playlists' as the URL to download every playlist on your profile:\n"
            "  spotify-dl download playlists\n\n"
            "Examples:\n"
            "  spotify-dl download 'spotify:track:abc123'\n\n"
            "  spotify-dl download playlists\n\n"
            "  spotify-dl download --from-file links.txt\n\n"
            "  spotify-dl download 'url1' 'url2' \\\n"
            "             --youtube-link 'yt_url1' 'yt_url2'\n\n"
            "  spotify-dl download 'url1' 'url2' 'url3' \\\n"
            "             --youtube-link _ 'yt_url2' _\n\n"
            "  spotify-dl download 'url1' 'url2' \\\n"
            "             --output ~/Music --quality 320 --dry-run"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    dl_parser.add_argument(
        "urls",
        nargs="*",
        metavar="URL",
        help="One or more Spotify track, album, or playlist URLs.",
    )
    dl_parser.add_argument(
        "--from-file",
        metavar="PATH",
        dest="from_file",
        help=(
            "Load Spotify URLs from a manifest file with [tracks], [playlists], "
            "and [albums] sections. Track lines may use 'spotify_url | youtube_url'."
        ),
    )
    dl_parser.add_argument(
        "--youtube-link",
        nargs="+",
        metavar="URL",
        dest="youtube_links",
        help=(
            "One or more YouTube URLs to use directly, bypassing the search step. "
            "Use '_' as a placeholder to skip a position and fall back to YouTube search. "
            "Count must exactly match the number of Spotify track URLs provided. "
            "Albums and playlists are not supported with this option."
        ),
    )

    add_shared_options(dl_parser)


# ─────────────────────────────────────────────────────────────────────────────
# Root parser
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="spotify-dl",
        description=(
            "spotify-dl — Download Spotify tracks, albums, and playlists via YouTube.\n\n"
            "Get started:\n"
            "  1. spotify-dl auth login\n"
            "  2. spotify-dl download '<spotify_url>'"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Commands:\n"
            "  auth        Manage Spotify authentication (login / logout / status)\n"
            "  config      Manage configuration (set / show / clear / clear-cookies)\n"
            "  profile     Show basic Spotify account information\n"
            "  playlists   List or sync library playlists (list / sync)\n"
            "  download    Download tracks, albums, or playlists by URL\n\n"
            "Run `spotify-dl <command> --help` for command-specific help."
        ),
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    build_auth_parser(subparsers)
    build_config_parser(subparsers)
    build_profile_parser(subparsers)
    build_playlists_parser(subparsers)
    build_download_parser(subparsers)

    return parser
