from __future__ import annotations

import click

from spotify_dl.commands import register_commands
from spotify_dl.commands.common import root_cli_options


class UrlOrCommandGroup(click.Group):
    def resolve_command(self, ctx: click.Context, args: list[str]):
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            return "download", self.commands["download"], args


@click.group(
    cls=UrlOrCommandGroup,
    invoke_without_command=True,
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)
@root_cli_options
@click.pass_context
def cli(ctx: click.Context, **kwargs) -> None:
    """Download Spotify tracks, albums, and playlists as tagged MP3 files."""
    if ctx.invoked_subcommand:
        return
    click.echo(ctx.get_help())


register_commands(cli)


if __name__ == "__main__":
    cli()
