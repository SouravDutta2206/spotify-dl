from __future__ import annotations

import click

from spotify_dl.commands import register_commands


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
@click.option("--output", "-o", "output_directory")
@click.option("--quality", "-q")
@click.option("--client-id")
@click.option("--client-secret")
@click.option("--youtube-cookies-from", "youtube_cookie_browser")
@click.option("--youtube-cookie-file", "youtube_cookie_file")
@click.option("--skip-existing/--no-skip-existing", default=True)
@click.option("--dry-run", is_flag=True)
@click.option("--verbose", "-v", is_flag=True)
@click.option("--concurrency", "-c", type=int)
@click.option("--youtube-link", "youtube_link", default=None, help="Use this YouTube URL instead of searching.")
@click.option("--make-playlist", is_flag=True, help="Create a local folder mirroring the Spotify playlist.")
@click.pass_context
def cli(ctx: click.Context, **kwargs) -> None:
    """Download Spotify tracks, albums, and playlists as tagged MP3 files."""
    if ctx.invoked_subcommand:
        return
    click.echo(ctx.get_help())


register_commands(cli)


if __name__ == "__main__":
    cli()
