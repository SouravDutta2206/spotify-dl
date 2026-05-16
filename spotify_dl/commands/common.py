from __future__ import annotations

import click

from spotify_dl.config import ConfigManager
from spotify_dl.exceptions import SpotifyDlError


def config_manager() -> ConfigManager:
    return ConfigManager()


def load_config(**overrides):
    return config_manager().load(**overrides)


def handle_spotify_dl_error(exc: SpotifyDlError) -> click.ClickException:
    return click.ClickException(str(exc))
