from __future__ import annotations

import sys

from spotify_dl.pipeline import DownloadPipeline
from spotify_dl.exceptions import SpotifyDlError
from spotify_dl.filesystem import FileSystem
from spotify_dl.logging import get_logger
from spotify_dl.models import AppConfig, DownloadOptions, TrackMetadata
from spotify_dl.source_cache import deserialize_tracks
from spotify_dl.spotify import SpotifyClient
from spotify_dl.cli_utils import normalize_download_options, spotify_client_from_options

logger = get_logger("sync")


def has_missing_track_files(
    filesystem: FileSystem,
    tracks: list[TrackMetadata],
    *,
    make_playlist: bool,
    playlist_name: str,
) -> bool:
    for track in tracks:
        if not filesystem.get_track_path(track).exists():
            return True
        if make_playlist and not filesystem.get_playlist_mirror_path(track, playlist_name).exists():
            return True
    return False


def run_sync(options: dict) -> None:
    download_options = normalize_download_options(options, force_skip_existing=True)
    config, spotify = spotify_client_from_options(download_options)
    cached_playlists = list(spotify.source_cache.iter_playlists())
    if not cached_playlists:
        print("No cached playlists found.")
        return
    filesystem = FileSystem(config.output_directory)
    make_playlist = download_options.make_playlist

    logger.info("Syncing %d cached playlist(s)", len(cached_playlists))
    print(f"\nSyncing {len(cached_playlists)} cached playlist(s)...\n")
    for playlist_id, _path in cached_playlists:
        _sync_playlist(
            playlist_id=playlist_id,
            config=config,
            spotify=spotify,
            filesystem=filesystem,
            download_options=download_options,
            make_playlist=make_playlist,
        )


def _sync_playlist(
    *,
    playlist_id: str,
    config: AppConfig,
    spotify: SpotifyClient,
    filesystem: FileSystem,
    download_options: DownloadOptions,
    make_playlist: bool,
) -> None:
    payload = spotify.source_cache.read_collection("playlist", playlist_id)
    if payload is None:
        print(f"  Skipping invalid cache: {playlist_id}")
        return

    cached_snapshot = payload.get("snapshot_id")
    try:
        header = spotify.get_playlist_header(playlist_id)
    except SpotifyDlError as exc:
        logger.error("Sync error for playlist %s: %s", playlist_id, exc)
        print(f"  Error ({playlist_id}): {exc}", file=sys.stderr)
        return

    current_snapshot = header.get("snapshot_id")
    playlist_name = header.get("name") or payload.get("source_name") or playlist_id
    snapshot_changed = cached_snapshot != current_snapshot

    if snapshot_changed:
        tracks = spotify.get_playlist(
            playlist_id,
            snapshot_id=current_snapshot,
            playlist_name=playlist_name,
        )
    else:
        tracks = deserialize_tracks(payload)

    needs_download = snapshot_changed or has_missing_track_files(
        filesystem,
        tracks,
        make_playlist=make_playlist,
        playlist_name=playlist_name,
    )
    if not needs_download:
        logger.debug("Up to date: %s (%s)", playlist_name, playlist_id)
        print(f"  Up to date: {playlist_name}")
        return

    if snapshot_changed:
        logger.info("Sync: %s — snapshot changed", playlist_name)
        print(f"  Updated: {playlist_name} (snapshot changed)")
    else:
        logger.info("Sync: %s — gap fill (missing files)", playlist_name)
        print(f"  Gap fill: {playlist_name} (missing files)")

    pipeline = DownloadPipeline(
        config,
        download_options,
        cover_cache=spotify.cover_cache,
        source_cache=spotify.source_cache,
    )
    pipeline.download_source(
        source_type="playlist",
        source_name=playlist_name,
        tracks=tracks,
    )
