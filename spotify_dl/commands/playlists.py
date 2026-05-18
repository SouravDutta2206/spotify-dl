from __future__ import annotations

import click

from spotify_dl.commands.common import config_manager, handle_spotify_dl_error, load_config
from spotify_dl.exceptions import SpotifyDlError
from spotify_dl.spotify import SpotifyClient
from spotify_dl.sync import run_sync


def _list_playlists() -> None:
    config = load_config()
    spotify = SpotifyClient(config, config_manager())
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
def list_cmd() -> None:
    """List your saved Spotify playlists."""
    try:
        _list_playlists()
    except SpotifyDlError as exc:
        raise handle_spotify_dl_error(exc) from exc


@playlists.command("sync")
@click.option("--output", "-o", "output_directory", help="Set the output directory for downloaded files.")
@click.option("--quality", "-q", help="Set the audio quality (e.g. 128, 192, 320).")
@click.option("--client-id", help="Spotify API client ID.")
@click.option("--client-secret", help="Spotify API client secret.")
@click.option("--youtube-cookies-from", "youtube_cookie_browser", help="Browser to extract YouTube cookies from.")
@click.option("--youtube-cookie-file", "youtube_cookie_file", help="Path to a cookies.txt file for YouTube.")
@click.option("--dry-run", is_flag=True, default=None, help="Simulate the download process without fetching files.")
@click.option("--verbose", "-v", is_flag=True, default=None, help="Enable verbose output.")
@click.option("--concurrency", "-c", type=int, help="Maximum number of concurrent downloads.")
@click.option("--make-playlist", is_flag=True, default=None, help="Create a local folder mirroring the Spotify playlist.")
@click.pass_context
def sync_cmd(ctx: click.Context, **kwargs) -> None:
    """Sync cached playlists with Spotify and download missing tracks."""
    root = ctx.parent.parent if ctx.parent and ctx.parent.parent else None
    parent_params = root.params if root else {}
    options = {**parent_params, **{key: value for key, value in kwargs.items() if value is not None}}
    options["skip_existing"] = True
    options.setdefault("dry_run", False)
    options.setdefault("verbose", False)
    options.setdefault("make_playlist", False)
    run_sync(options)


def register_playlists_command(cli: click.Group) -> None:
    cli.add_command(playlists)
