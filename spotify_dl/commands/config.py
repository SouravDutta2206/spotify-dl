from __future__ import annotations

import json

import click

from spotify_dl.commands.common import config_manager


@click.group("config")
def config_cmd() -> None:
    """Manage spotify-dl configuration."""


@config_cmd.command("set")
@click.option("--client-id", help="Spotify API client ID.")
@click.option("--client-secret", help="Spotify API client secret.")
@click.option("--output-dir", help="Default output directory for downloads.")
@click.option("--quality", type=click.Choice(["0", "128", "192", "320"]), help="Default audio quality.")
@click.option("--youtube-cookies-from", help="Browser to extract YouTube cookies from.")
@click.option("--youtube-cookie-file", help="Path to a cookies.txt file for YouTube.")
@click.option("--auth-port", type=int, help="Port to use for the local authentication callback server.")
@click.option("--concurrency", type=int, help="Maximum number of concurrent downloads.")
def config_set(**kwargs) -> None:
    """Set configuration values."""
    partial: dict[str, object] = {}
    spotify: dict[str, object] = {}
    output: dict[str, object] = {}
    youtube: dict[str, object] = {}
    auth: dict[str, object] = {}
    if kwargs["client_id"]:
        spotify["client_id"] = kwargs["client_id"]
    if kwargs["client_secret"]:
        spotify["client_secret"] = kwargs["client_secret"]
    if kwargs["output_dir"]:
        output["directory"] = kwargs["output_dir"]
    if kwargs["quality"]:
        output["quality"] = kwargs["quality"]
    if kwargs["youtube_cookies_from"]:
        youtube["cookie_browser"] = kwargs["youtube_cookies_from"]
    if kwargs["youtube_cookie_file"]:
        youtube["cookie_file"] = kwargs["youtube_cookie_file"]
    if kwargs["auth_port"]:
        auth["callback_port"] = kwargs["auth_port"]
    if kwargs["concurrency"]:
        partial["concurrency"] = kwargs["concurrency"]
    if spotify:
        partial["spotify"] = spotify
    if output:
        partial["output"] = output
    if youtube:
        partial["youtube"] = youtube
    if auth:
        partial["auth"] = auth
    config_manager().save(partial)
    click.echo("Configuration saved.")


@config_cmd.command("show")
def config_show() -> None:
    """Show the current configuration (with secrets masked)."""
    click.echo(json.dumps(config_manager().masked(), indent=2))


@config_cmd.command("clear")
def config_clear() -> None:
    """Clear all configuration values."""
    config_manager().clear()
    click.echo("Configuration cleared.")


@config_cmd.command("clear-cookies")
def config_clear_cookies() -> None:
    """Clear saved YouTube cookies."""
    config_manager().clear_cookies()
    click.echo("YouTube cookie configuration cleared.")


def register_config_command(cli: click.Group) -> None:
    cli.add_command(config_cmd)
