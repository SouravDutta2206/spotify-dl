from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
import sys

import click

from spotify_dl.auth import AuthManager
from spotify_dl.config import ConfigManager
from spotify_dl.exceptions import ConfigError, SpotifyDlError
from spotify_dl.filesystem import FileSystem
from spotify_dl.pipeline import DownloadPipeline
from spotify_dl.source_cache import CoverCache
from spotify_dl.spotify import SpotifyClient

PLAYLIST_MAX_WORKERS = 5


class UrlOrCommandGroup(click.Group):
    def resolve_command(self, ctx: click.Context, args: list[str]):
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            return "download", self.commands["download"], args


def _config_manager() -> ConfigManager:
    return ConfigManager()


def _load_config(**overrides):
    return _config_manager().load(**overrides)


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
@click.pass_context
def cli(ctx: click.Context, **kwargs) -> None:
    """Download Spotify tracks, albums, and playlists as tagged MP3 files."""
    if ctx.invoked_subcommand:
        return
    click.echo(ctx.get_help())


def _run_download(url: str, options: dict) -> None:
    try:
        config = _load_config(
            client_id=options["client_id"],
            client_secret=options["client_secret"],
            output_directory=options["output_directory"],
            quality=options["quality"],
            youtube_cookie_browser=options["youtube_cookie_browser"],
            youtube_cookie_file=options["youtube_cookie_file"],
            concurrency=options["concurrency"],
        )
        spotify = SpotifyClient(config, _config_manager())
        source_type, source_name, tracks = spotify.resolve_url(url)
        youtube_link = options.get("youtube_link")
        if youtube_link and source_type != "track":
            raise click.ClickException("--youtube-link can only be used with a single Spotify track URL.")
        click.echo(f"\n  {source_type.title()}: {source_name}")
        click.echo(f"  Tracks: {len(tracks)}\n")
        results = _process_tracks(
            config=config,
            source_type=source_type,
            tracks=tracks,
            options=options,
            cover_cache=spotify.cover_cache,
            youtube_link=youtube_link,
        )
        done = sum(1 for result in results if result.status == "done")
        skipped = sum(1 for result in results if result.status == "skipped")
        failed = sum(1 for result in results if result.status == "failed")
        click.echo(f"\n  Done. {done} downloaded, {skipped} skipped, {failed} failed.")
        click.echo(f"  Output: {config.output_directory}")
    except SpotifyDlError as exc:
        raise click.ClickException(str(exc)) from exc


def _process_tracks(
    *,
    config,
    source_type: str,
    tracks: list,
    options: dict,
    cover_cache: CoverCache | None = None,
    youtube_link: str | None = None,
):
    if source_type != "playlist" or options["dry_run"] or len(tracks) <= 1:
        pipeline = DownloadPipeline(config, cover_cache=cover_cache, verbose=options["verbose"])
        results = []
        for index, track in enumerate(tracks, start=1):
            result = pipeline.process_track(
                track,
                skip_existing=options["skip_existing"],
                dry_run=options["dry_run"],
                youtube_url=youtube_link,
            )
            results.append(result)
            _print_track_result(index, len(tracks), result)
        return results

    workers = min(max(1, int(config.concurrency)), PLAYLIST_MAX_WORKERS, len(tracks))
    click.echo(f"  Processing playlist with {workers} concurrent workers.\n")
    results = []
    completed = 0
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = {
        executor.submit(
            DownloadPipeline(config, cover_cache=cover_cache, verbose=options["verbose"]).process_track,
            track,
            skip_existing=options["skip_existing"],
            dry_run=False,
        ): track
        for track in tracks
    }
    try:
        for future in as_completed(futures):
            completed += 1
            result = future.result()
            results.append(result)
            _print_track_result(completed, len(tracks), result)
    except KeyboardInterrupt:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        click.echo("\n  Aborted.")
        os._exit(130)
    else:
        executor.shutdown(wait=True)
    return results


def _print_track_result(index: int, total: int, result) -> None:
    marker = {"done": "done", "skipped": "skipped", "failed": "failed"}[result.status]
    click.echo(f"  [{index}/{total}] {result.track.title} ... {marker}")
    if result.error:
        click.echo(f"      {result.error}", err=True)


@cli.command("download", hidden=True)
@click.argument("url")
@click.option("--output", "-o", "output_directory")
@click.option("--quality", "-q")
@click.option("--client-id")
@click.option("--client-secret")
@click.option("--youtube-cookies-from", "youtube_cookie_browser")
@click.option("--youtube-cookie-file", "youtube_cookie_file")
@click.option("--skip-existing/--no-skip-existing", default=None)
@click.option("--dry-run", is_flag=True, default=None)
@click.option("--verbose", "-v", is_flag=True, default=None)
@click.option("--concurrency", "-c", type=int)
@click.option("--youtube-link", "youtube_link", default=None, help="Use this YouTube URL instead of searching.")
@click.pass_context
def download(ctx: click.Context, url: str, **kwargs) -> None:
    parent = ctx.parent.params if ctx.parent else {}
    options = {**parent, **{key: value for key, value in kwargs.items() if value is not None}}
    options.setdefault("skip_existing", True)
    options.setdefault("dry_run", False)
    options.setdefault("verbose", False)
    options.setdefault("youtube_link", None)
    _run_download(url, options)


@cli.group("config")
def config_cmd() -> None:
    """Manage spotify-dl configuration."""


@config_cmd.command("set")
@click.option("--client-id")
@click.option("--client-secret")
@click.option("--output-dir")
@click.option("--quality", type=click.Choice(["0", "128", "192", "320"]))
@click.option("--youtube-cookies-from")
@click.option("--youtube-cookie-file")
@click.option("--auth-port", type=int)
@click.option("--concurrency", type=int)
def config_set(**kwargs) -> None:
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
    _config_manager().save(partial)
    click.echo("Configuration saved.")


@config_cmd.command("show")
def config_show() -> None:
    click.echo(json.dumps(_config_manager().masked(), indent=2))


@config_cmd.command("clear")
def config_clear() -> None:
    _config_manager().clear()
    click.echo("Configuration cleared.")


@config_cmd.command("clear-cookies")
def config_clear_cookies() -> None:
    _config_manager().clear_cookies()
    click.echo("YouTube cookie configuration cleared.")


@cli.group()
def auth() -> None:
    """Manage Spotify user authentication."""


@auth.command("login")
def auth_login() -> None:
    try:
        manager = _config_manager()
        click.echo(AuthManager(manager.load(), manager).login())
    except SpotifyDlError as exc:
        raise click.ClickException(str(exc)) from exc


@auth.command("logout")
def auth_logout() -> None:
    manager = _config_manager()
    config = manager.load(require_credentials=False)
    AuthManager(config, manager).logout()
    click.echo("Logged out.")


@auth.command("status")
def auth_status() -> None:
    try:
        config = _config_manager().load(require_credentials=False)
        click.echo(f"Spotify API credentials: {'configured' if config.spotify_client_id else 'missing'}")
        click.echo(f"User account: {'logged in' if config.spotify_user_access_token else 'not logged in'}")
        if config.spotify_user_token_expiry:
            click.echo(f"Token expires: {config.spotify_user_token_expiry.isoformat()}")
    except ConfigError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.option("--download", "download", is_flag=True)
def playlists(download: bool) -> None:
    try:
        config = _load_config()
        spotify = SpotifyClient(config, _config_manager())
        items = spotify.list_user_playlists()
        for index, playlist in enumerate(items, start=1):
            click.echo(
                f"{index:>2}. {playlist.name}  "
                f"({playlist.track_count} tracks, {playlist.visibility})  {playlist.spotify_url}"
            )
        if download:
            click.echo("\nInteractive playlist download selection is not implemented yet.")
    except SpotifyDlError as exc:
        raise click.ClickException(str(exc)) from exc



if __name__ == "__main__":
    cli()
