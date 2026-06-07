from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from spotify_dl.auth import AuthManager
from spotify_dl.cli_utils import (
    _CONFIG_KEY_MAP,
    _CONFIG_VALIDATORS,
    build_parser,
    spotify_client_from_options,
)
from spotify_dl.config import ConfigManager
from spotify_dl.exceptions import SpotifyDlError
from spotify_dl.logging import get_logger, setup_session_logging
from spotify_dl.manifest import ManifestParseError, parse_download_manifest
from spotify_dl.pipeline import COLLECTION_SOURCE_TYPES, run_download
from spotify_dl.sync import run_sync
from spotify_dl.spotify import BATCH_TRACK_THRESHOLD, parse_spotify_url


YOUTUBE_LINK_SKIP = "_"


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

    # "download playlists" shortcut — skip normal URL validation
    if getattr(args, "urls", None) == ["playlists"]:
        return

    if args.from_file:
        if args.urls:
            parser.error("URL arguments cannot be combined with --from-file.")
        if args.youtube_links is not None:
            parser.error("--youtube-link cannot be combined with --from-file.")
        try:
            args.download_manifest = parse_download_manifest(args.from_file)
        except ManifestParseError as exc:
            parser.error(str(exc))
        return

    if not args.urls:
        parser.error("download requires at least one Spotify URL or --from-file.")

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
# Command Handlers
# ─────────────────────────────────────────────────────────────────────────────

def _handle_auth(args: argparse.Namespace) -> None:
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


def _handle_config(args: argparse.Namespace) -> None:
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


def _handle_playlists(args: argparse.Namespace) -> None:
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


def _handle_profile(args: argparse.Namespace) -> None:
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


def _download_all_playlists(args: argparse.Namespace) -> None:
    """Fetch all user playlists and download each through the standard pipeline."""
    opts = dict(vars(args))
    opts["youtube_link"] = None
    opts["youtube_link_map"] = None

    _, spotify = spotify_client_from_options(opts)
    playlists = spotify.list_user_playlists()
    if not playlists:
        print("No playlists found on your profile.")
        return

    print(f"\n  Found {len(playlists)} playlist(s) on your profile.\n")
    for index, pl in enumerate(playlists, start=1):
        print(f"  {index:>2}. {pl.name}  ({pl.track_count} tracks)  {pl.spotify_url}")
    print()

    for index, pl in enumerate(playlists, start=1):
        print(f"\n{'='*60}")
        print(f"  [{index}/{len(playlists)}] Downloading playlist: {pl.name}")
        print(f"{'='*60}")
        run_download(pl.spotify_url, opts)

    print(f"\n  All {len(playlists)} playlist(s) processed.")


def _dispatch_download(args: argparse.Namespace) -> None:
    """Partition Spotify URLs and dispatch downloads."""

    # ── Handle "download playlists" shortcut ──────────────────────────────
    if getattr(args, "urls", None) == ["playlists"]:
        _download_all_playlists(args)
        return

    opts = dict(vars(args))
    opts["youtube_link"] = None
    opts["youtube_link_map"] = None

    # ── Normalize input source ────────────────────────────────────────────
    if args.from_file:
        manifest = (
            getattr(args, "download_manifest", None)
            or parse_download_manifest(args.from_file)
        )
        urls = [t.spotify_url for t in manifest.tracks] + manifest.collections
        yt_pairs = {
            parse_spotify_url(t.spotify_url)[1]: t.youtube_url
            for t in manifest.tracks
            if t.youtube_url
        }
        if yt_pairs:
            opts["youtube_link_map"] = yt_pairs
        youtube_links = None       # disable per-track CLI path
    else:
        urls = args.urls
        youtube_links = args.youtube_links
        if youtube_links:
            opts["youtube_link_map"] = {
                parse_spotify_url(url)[1]: (yt if yt != YOUTUBE_LINK_SKIP else None)
                for url, yt in zip(urls, youtube_links)
            }

    # ── Partition & dispatch (unchanged) ──────────────────────────────────
    track_urls: list[str] = []
    collection_urls: list[str] = []
    for url in urls:
        kind, _ = parse_spotify_url(url)
        (track_urls if kind == "track" else collection_urls).append(url)

    if track_urls:
        if len(track_urls) > BATCH_TRACK_THRESHOLD:
            run_download(track_urls, opts)
        elif youtube_links:
            for url, yt in zip(track_urls, youtube_links):
                opts_single = dict(opts)
                opts_single["youtube_link"] = yt if yt != YOUTUBE_LINK_SKIP else None
                run_download(url, opts_single)
        else:
            for url in track_urls:
                run_download(url, opts)

    for url in collection_urls:
        run_download(url, opts)


_HANDLERS = {
    "auth": _handle_auth,
    "config": _handle_config,
    "playlists": _handle_playlists,
    "profile": _handle_profile,
    "download": _dispatch_download,
}


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    setup_session_logging()
    logger = get_logger("main")
    t0 = time.monotonic()

    # Intercept Spotify URLs passed directly as the first argument (fallback behavior)
    commands = {"auth", "config", "profile", "playlists", "download", "-h", "--help"}
    if len(sys.argv) > 1 and sys.argv[1] not in commands and not sys.argv[1].startswith("-"):
        sys.argv.insert(1, "download")

    logger.info("Session started: %s", " ".join(sys.argv))

    parser = build_parser()

    # `spotify-dl` with no arguments shows full help (same as --help)
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
    logger.debug("Parsed command: %s, args: %s", args.command, vars(args))

    # Post-parse validation
    if args.command == "download":
        validate_download(args, parser)

    elif args.command == "playlists" and args.playlists_command == "sync":
        validate_shared(args, parser)

    # ── Dispatch ──────────────────────────────────────────────────────────────
    handler = _HANDLERS.get(args.command)
    if not handler:
        parser.print_help()
        sys.exit(0)

    try:
        handler(args)
    except SpotifyDlError as exc:
        logger.error("SpotifyDlError: %s", exc)
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Session aborted by user")
        print("\n  Aborted.", file=sys.stderr)
        sys.exit(130)
    finally:
        logger.info("Session finished in %.1fs", time.monotonic() - t0)


if __name__ == "__main__":
    main()
