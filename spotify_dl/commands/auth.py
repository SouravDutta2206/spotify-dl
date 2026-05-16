from __future__ import annotations

import click

from spotify_dl.auth import AuthManager
from spotify_dl.commands.common import config_manager, handle_spotify_dl_error
from spotify_dl.exceptions import ConfigError, SpotifyDlError


@click.group()
def auth() -> None:
    """Manage Spotify user authentication."""


@auth.command("login")
def auth_login() -> None:
    """Log in to your Spotify account."""
    try:
        manager = config_manager()
        click.echo(AuthManager(manager.load(), manager).login())
    except SpotifyDlError as exc:
        raise handle_spotify_dl_error(exc) from exc


@auth.command("logout")
def auth_logout() -> None:
    """Log out of your Spotify account."""
    manager = config_manager()
    config = manager.load(require_credentials=False)
    AuthManager(config, manager).logout()
    click.echo("Logged out.")


@auth.command("status")
def auth_status() -> None:
    """Show your current Spotify authentication status."""
    try:
        config = config_manager().load(require_credentials=False)
        click.echo(f"Spotify API credentials: {'configured' if config.spotify_client_id else 'missing'}")
        click.echo(f"User account: {'logged in' if config.spotify_user_access_token else 'not logged in'}")
        if config.spotify_user_token_expiry:
            click.echo(f"Token expires: {config.spotify_user_token_expiry.isoformat()}")
    except ConfigError as exc:
        raise handle_spotify_dl_error(exc) from exc


def register_auth_command(cli: click.Group) -> None:
    cli.add_command(auth)
