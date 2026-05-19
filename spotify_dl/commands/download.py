from __future__ import annotations

import click

from spotify_dl.commands.common import (
    download_command_options,
    merge_cli_options,
    normalize_download_options,
)
from spotify_dl.pipeline import run_download

@click.command("download")
@click.argument("url")
@download_command_options
@click.pass_context
def download(ctx: click.Context, url: str, **kwargs) -> None:
    """Download a Spotify track, album, or playlist URL."""
    options = normalize_download_options(merge_cli_options(ctx, **kwargs))
    run_download(url, options)

def register_download_command(cli: click.Group) -> None:
    cli.add_command(download)