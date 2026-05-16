from __future__ import annotations

import click

from spotify_dl.commands.common import config_manager, handle_spotify_dl_error, load_config
from spotify_dl.exceptions import SpotifyDlError
from spotify_dl.spotify import SpotifyClient


@click.command()
def playlists() -> None:
    """List your saved Spotify playlists."""
    try:
        config = load_config()
        spotify = SpotifyClient(config, config_manager())
        items = spotify.list_user_playlists()
        for index, playlist in enumerate(items, start=1):
            click.echo(
                f"{index:>2}. {playlist.name}  "
                f"({playlist.track_count} tracks, {playlist.visibility})  {playlist.spotify_url}"
            )
    except SpotifyDlError as exc:
        raise handle_spotify_dl_error(exc) from exc


def register_playlists_command(cli: click.Group) -> None:
    cli.add_command(playlists)
