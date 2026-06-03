from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from spotify_dl.auth import AuthManager
from spotify_dl.cli_utils import spotify_client_from_options
from spotify_dl.config import ConfigManager
from spotify_dl.exceptions import SpotifyDlError
from spotify_dl.pipeline import COLLECTION_SOURCE_TYPES, run_download, run_batch_download
from spotify_dl.sync import run_sync
from spotify_dl.spotify import BATCH_TRACK_THRESHOLD, parse_spotify_url


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
    "quality": ({"0", "128", "192", "320"}, None, "Audio quality must be one of: 0, 128, 192, 320"),
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
            "--youtube-link to skip the search step. When --youtube-link is used,\n"
            "its count must exactly match the number of Spotify track URLs given.\n"
            "Albums and playlists are not supported with --youtube-link.\n\n"
            "Examples:\n"
            "  spotify-dl download 'spotify:track:abc123'\n\n"
            "  spotify-dl download 'url1' 'url2' \\\n"
            "             --youtube-link 'yt_url1' 'yt_url2'\n\n"
            "  spotify-dl download 'url1' 'url2' \\\n"
            "             --output ~/Music --quality 320 --dry-run"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    dl_parser.add_argument(
        "urls",
        nargs="+",
        metavar="URL",
        help="One or more Spotify track, album, or playlist URLs.",
    )
    dl_parser.add_argument(
        "--youtube-link",
        nargs="+",
        metavar="URL",
        dest="youtube_links",
        help=(
            "One or more YouTube URLs to use directly, bypassing the search step. "
            "Count must exactly match the number of Spotify track URLs provided. "
            "Albums and playlists are not supported with this option."
        ),
    )

    add_shared_options(dl_parser)


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def validate_shared(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if hasattr(args, "concurrency") and args.concurrency is not None and args.concurrency < 1:
        parser.error("--concurrency must be at least 1.")

    if hasattr(args, "auth_port") and args.auth_port is not None and not (1024 <= args.auth_port <= 65535):
        parser.error("--auth-port must be between 1024 and 65535.")

def validate_download(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    validate_shared(args, parser)

    source_types = set()
    for url in args.urls:
        source_type, _ = parse_spotify_url(url)
        if source_type is None:
            parser.error(f"Not a valid Spotify track, album, or playlist URL: {url}")
        source_types.add(source_type)

    if args.youtube_links is not None:
        n_spotify = len(args.urls)
        n_youtube = len(args.youtube_links)
        if n_spotify != n_youtube:
            parser.error(
                f"Mismatched link count: {n_spotify} Spotify URL(s) provided but "
                f"{n_youtube} YouTube URL(s) given via --youtube-link. "
                f"Counts must match exactly."
            )
        if source_types & COLLECTION_SOURCE_TYPES:
            parser.error(
                "--youtube-link is only supported with Spotify track URLs. "
                "Album and playlist URLs must be downloaded without --youtube-link."
            )


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


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — retrieve a named subparser for error context
# ─────────────────────────────────────────────────────────────────────────────

def _get_subparser(
    parser: argparse.ArgumentParser, *names: str
) -> argparse.ArgumentParser:
    """Walk down the subparser tree: _get_subparser(parser, 'download')."""
    current = parser
    for name in names:
        for action in current._subparsers._actions:
            if hasattr(action, "_name_parser_map") and name in action._name_parser_map:
                current = action._name_parser_map[name]
                break
    return current


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # Intercept Spotify URLs passed directly as the first argument (fallback behavior)
    commands = {"auth", "config", "profile", "playlists", "download", "-h", "--help"}
    if len(sys.argv) > 1 and sys.argv[1] not in commands and not sys.argv[1].startswith("-"):
        sys.argv.insert(1, "download")

    parser = build_parser()

    # `spotify-dl` with no arguments shows full help (same as --help)
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()

    # Post-parse validation
    if args.command == "download":
        validate_download(args, _get_subparser(parser, "download"))

    elif args.command == "playlists" and args.playlists_command == "sync":
        validate_shared(args, _get_subparser(parser, "playlists", "sync"))

    # ── Dispatch ──────────────────────────────────────────────────────────────
    try:
        if args.command == "auth":
            manager = ConfigManager()
            if args.auth_command == "login":
                
                print(AuthManager(manager.load(), manager).login())
            elif args.auth_command == "logout":
                
                config = manager.load(require_credentials=False)
                AuthManager(config, manager).logout()
                print("Logged out.")
            elif args.auth_command == "status":
                config = manager.load(require_credentials=False)
                print(f"Spotify API credentials: {'configured' if config.spotify_client_id else 'missing'}")
                print(f"User account: {'logged in' if config.spotify_user_access_token else 'not logged in'}")
                if config.spotify_user_token_expiry:
                    print(f"Token expires: {config.spotify_user_token_expiry.isoformat()}")

        elif args.command == "config":
            manager = ConfigManager()
            if args.config_command == "set":
                key = args.key.lower().replace("_", "-")
                if key not in _CONFIG_KEY_MAP:
                    sys.exit(f"Error: Unknown configuration key: {args.key}")

                value: Any = args.value
                if key in _CONFIG_VALIDATORS:
                    choices, cast, error_msg = _CONFIG_VALIDATORS[key]
                    if choices and value not in choices:
                        sys.exit(f"Error: {error_msg}")
                    if cast:
                        try:
                            value = cast(value)
                        except ValueError:
                            sys.exit(f"Error: {error_msg}")

                path = _CONFIG_KEY_MAP[key]
                if len(path) == 1:
                    partial = {path[0]: value}
                else:
                    partial = {path[0]: {path[1]: value}}

                manager.save(partial)
                print("Configuration saved.")

            elif args.config_command == "show":
                print(json.dumps(manager.masked(), indent=2))
            elif args.config_command == "clear":
                manager.clear()
                print("Configuration cleared.")
            elif args.config_command == "clear-cookies":
                manager.clear_cookies()
                print("YouTube cookie configuration cleared.")

        elif args.command == "playlists":
            if args.playlists_command == "list":
                options = vars(args)
                _, spotify = spotify_client_from_options(options)
                items = spotify.list_user_playlists()
                for index, playlist in enumerate(items, start=1):
                    print(
                        f"{index:>2}. {playlist.name}  "
                        f"({playlist.track_count} tracks, {playlist.visibility})  {playlist.spotify_url}"
                    )
            elif args.playlists_command == "sync":
                
                options = vars(args)
                run_sync(options)

        elif args.command == "profile":
            options = vars(args)
            _, spotify = spotify_client_from_options(options)
            profile = spotify.get_current_user_profile()
            print(f"Display name: {profile.display_name}")
            print(f"Spotify user ID: {profile.spotify_user_id}")
            print(f"Account type: {profile.account_type}")
            print(f"Account ID: {profile.account_id}")
            print(f"Country: {profile.country}")
            print(f"Email: {profile.email}")
            print(f"Followers: {profile.followers}")
            print(f"Explicit filter: {profile.explicit_filter_enabled}")

        elif args.command == "download":
            
            if args.youtube_links:
                for spotify_url, yt_link in zip(args.urls, args.youtube_links):
                    opts = dict(vars(args))
                    opts["youtube_link"] = yt_link
                    run_download(spotify_url, opts)
            else:
                track_urls = []
                collection_urls = []
                for url in args.urls:
                    kind, _ = parse_spotify_url(url)
                    if kind == "track":
                        track_urls.append(url)
                    else:
                        collection_urls.append(url)

                opts = dict(vars(args))
                opts["youtube_link"] = None

                if len(track_urls) > BATCH_TRACK_THRESHOLD:
                    run_batch_download(track_urls, opts)
                else:
                    for url in track_urls:
                        run_download(url, opts)

                for url in collection_urls:
                    run_download(url, opts)


    except SpotifyDlError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n  Aborted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
