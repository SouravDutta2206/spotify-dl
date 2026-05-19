from __future__ import annotations

import click

from spotify_dl.commands.auth import register_auth_command
from spotify_dl.commands.config import register_config_command
from spotify_dl.commands.download import register_download_command
from spotify_dl.commands.playlists import register_playlists_command

def register_commands(cli: click.Group) -> None:
    register_download_command(cli)
    register_config_command(cli)
    register_auth_command(cli)
    register_playlists_command(cli)