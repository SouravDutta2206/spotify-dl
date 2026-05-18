from __future__ import annotations

import click

from spotify_dl.commands.common import (
    handle_spotify_dl_error,
    merge_cli_options,
    normalize_download_options,
    spotify_client_from_options,
    sync_command_options,
)
from spotify_dl.exceptions import SpotifyDlError
from spotify_dl.sync import run_sync


def _list_playlists(options: dict) -> None:
    _, spotify = spotify_client_from_options(options)
    items = spotify.list_user_playlists()
    for index, playlist in enumerate(items, start=1):
        click.echo(
            f"{index:>2}. {playlist.name}  "
            f"({playlist.track_count} tracks, {playlist.visibility})  {playlist.spotify_url}"
        )


@click.group()
def playlists() -> None:
    """Manage Spotify playlists."""


@playlists.command("list")
@click.pass_context
def list_cmd(ctx: click.Context, **kwargs) -> None:
    """List your saved Spotify playlists."""
    try:
        _list_playlists(merge_cli_options(ctx, **kwargs))
    except SpotifyDlError as exc:
        raise handle_spotify_dl_error(exc) from exc


@playlists.command("sync")
@sync_command_options
@click.pass_context
def sync_cmd(ctx: click.Context, **kwargs) -> None:
    """Sync cached playlists with Spotify and download missing tracks."""
    options = normalize_download_options(
        merge_cli_options(ctx, **kwargs),
        force_skip_existing=True,
    )
    run_sync(options)


def register_playlists_command(cli: click.Group) -> None:
    cli.add_command(playlists)
