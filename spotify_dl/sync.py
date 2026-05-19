from __future__ import annotations

import click

from spotify_dl.commands.common import (
    handle_spotify_dl_error,
    normalize_download_options,
    spotify_client_from_options,
)
from spotify_dl.pipeline import download_tracks
from spotify_dl.exceptions import SpotifyDlError
from spotify_dl.filesystem import FileSystem
from spotify_dl.models import AppConfig, TrackMetadata
from spotify_dl.spotify import SpotifyClient


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
    try:
        download_options = normalize_download_options(options, force_skip_existing=True)
        config, spotify = spotify_client_from_options(download_options)
        cached_playlists = list(spotify.source_cache.iter_cached_playlists())
        if not cached_playlists:
            click.echo("No cached playlists found.")
            return
        filesystem = FileSystem(config.output_directory)
        make_playlist = bool(download_options.get("make_playlist"))

        click.echo(f"\nSyncing {len(cached_playlists)} cached playlist(s)...\n")
        for playlist_id, _path in cached_playlists:
            _sync_playlist(
                playlist_id=playlist_id,
                config=config,
                spotify=spotify,
                filesystem=filesystem,
                download_options=download_options,
                make_playlist=make_playlist,
            )
    except SpotifyDlError as exc:
        raise handle_spotify_dl_error(exc) from exc


def _sync_playlist(
    *,
    playlist_id: str,
    config: AppConfig,
    spotify: SpotifyClient,
    filesystem: FileSystem,
    download_options: dict,
    make_playlist: bool,
) -> None:
    payload = spotify.source_cache.read_playlist_payload(playlist_id)
    if payload is None:
        click.echo(f"  Skipping invalid cache: {playlist_id}")
        return

    cached_snapshot = payload.get("snapshot_id")
    try:
        header = spotify.get_playlist_header(playlist_id)
    except SpotifyDlError as exc:
        click.echo(f"  Error ({playlist_id}): {exc}", err=True)
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
        cached = spotify.source_cache.load(
            kind="playlist",
            source_id=playlist_id,
            snapshot_id=current_snapshot,
        )
        if cached is None:
            click.echo(f"  Error ({playlist_name}): could not load cached tracks", err=True)
            return
        tracks = cached[1]

    needs_download = snapshot_changed or has_missing_track_files(
        filesystem,
        tracks,
        make_playlist=make_playlist,
        playlist_name=playlist_name,
    )
    if not needs_download:
        click.echo(f"  Up to date: {playlist_name}")
        return

    if snapshot_changed:
        click.echo(f"  Updated: {playlist_name} (snapshot changed)")
    else:
        click.echo(f"  Gap fill: {playlist_name} (missing files)")

    download_tracks(
        config=config,
        source_type="playlist",
        source_name=playlist_name,
        tracks=tracks,
        options=download_options,
        cover_cache=spotify.cover_cache,
    )
