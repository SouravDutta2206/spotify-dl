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
@click.option("--output", "-o", "output_directory", help="Set the output directory for downloaded files.")
@click.option("--quality", "-q", help="Set the audio quality (e.g. 128, 192, 320).")
@click.option("--client-id", help="Spotify API client ID.")
@click.option("--client-secret", help="Spotify API client secret.")
@click.option("--youtube-cookies-from", "youtube_cookie_browser", help="Browser to extract YouTube cookies from.")
@click.option("--youtube-cookie-file", "youtube_cookie_file", help="Path to a cookies.txt file for YouTube.")
@click.option("--skip-existing/--no-skip-existing", default=True, help="Skip downloading files that already exist.")
@click.option("--dry-run", is_flag=True, help="Simulate the download process without fetching files.")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output.")
@click.option("--concurrency", "-c", type=int, help="Maximum number of concurrent downloads.")
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
