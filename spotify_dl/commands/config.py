from __future__ import annotations

import json

import click

from spotify_dl.commands.common import (
    config_manager,
    config_set_command_options,
    merge_cli_options,
    options_to_config_partial,
)


@click.group("config")
def config_cmd() -> None:
    """Manage spotify-dl configuration."""


@config_cmd.command("set")
@config_set_command_options
@click.pass_context
def config_set(ctx: click.Context, **kwargs) -> None:
    """Set configuration values."""
    options = merge_cli_options(ctx, **kwargs)
    partial = options_to_config_partial(options)
    if not partial:
        raise click.ClickException("No configuration values provided.")
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
