from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import os

import click

from spotify_dl.commands.common import config_manager, handle_spotify_dl_error, load_config
from spotify_dl.exceptions import SpotifyDlError
from spotify_dl.filesystem import FileSystem
from spotify_dl.pipeline import DownloadPipeline
from spotify_dl.source_cache import CoverCache
from spotify_dl.spotify import SpotifyClient

COLLECTION_MAX_WORKERS = 10
CONCURRENT_SOURCE_TYPES = {"album", "playlist"}


def run_download(url: str, options: dict) -> None:
    try:
        config = load_config(
            client_id=options["client_id"],
            client_secret=options["client_secret"],
            output_directory=options["output_directory"],
            quality=options["quality"],
            youtube_cookie_browser=options["youtube_cookie_browser"],
            youtube_cookie_file=options["youtube_cookie_file"],
            concurrency=options["concurrency"],
        )
        spotify = SpotifyClient(config, config_manager())
        source_type, source_name, tracks = spotify.resolve_url(url)
        youtube_link = options.get("youtube_link")
        if youtube_link and source_type != "track":
            raise click.ClickException("--youtube-link can only be used with a single Spotify track URL.")
        click.echo(f"\n  {source_type.title()}: {source_name}")
        click.echo(f"  Tracks: {len(tracks)}\n")
        make_playlist = options.get("make_playlist", False)
        playlist_dir = None
        if make_playlist and source_type == "playlist":
            playlist_dir = FileSystem(config.output_directory).get_playlist_directory(source_name)
        results = process_tracks(
            config=config,
            source_type=source_type,
            tracks=tracks,
            options=options,
            cover_cache=spotify.cover_cache,
            youtube_link=youtube_link,
            playlist_dir=playlist_dir,
        )
        done = sum(1 for result in results if result.status == "done")
        skipped = sum(1 for result in results if result.status == "skipped")
        failed = sum(1 for result in results if result.status == "failed")
        click.echo(f"\n  Done. {done} downloaded, {skipped} skipped, {failed} failed.")
        click.echo(f"  Output: {config.output_directory}")
    except SpotifyDlError as exc:
        raise handle_spotify_dl_error(exc) from exc


def process_tracks(
    *,
    config,
    source_type: str,
    tracks: list,
    options: dict,
    cover_cache: CoverCache | None = None,
    youtube_link: str | None = None,
    playlist_dir=None,
):
    if source_type not in CONCURRENT_SOURCE_TYPES or options["dry_run"] or len(tracks) <= 1:
        pipeline = DownloadPipeline(
            config,
            cover_cache=cover_cache,
            verbose=options["verbose"],
            playlist_dir=playlist_dir,
        )
        results = []
        for index, track in enumerate(tracks, start=1):
            result = pipeline.process_track(
                track,
                skip_existing=options["skip_existing"],
                dry_run=options["dry_run"],
                youtube_url=youtube_link,
            )
            results.append(result)
            print_track_result(index, len(tracks), result)
        return results

    workers = min(max(1, int(config.concurrency)), COLLECTION_MAX_WORKERS, len(tracks))
    click.echo(f"  Processing {source_type} with {workers} concurrent workers.\n")
    results = []
    completed = 0
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = {
        executor.submit(
            DownloadPipeline(
                config,
                cover_cache=cover_cache,
                verbose=options["verbose"],
                playlist_dir=playlist_dir,
            ).process_track,
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
            print_track_result(completed, len(tracks), result)
    except KeyboardInterrupt:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        click.echo("\n  Aborted.")
        os._exit(130)
    else:
        executor.shutdown(wait=True)
    return results


def print_track_result(index: int, total: int, result) -> None:
    marker = {"done": "done", "skipped": "skipped", "failed": "failed"}[result.status]
    click.echo(f"  [{index}/{total}] {result.track.title} ... {marker}")
    if result.error:
        click.echo(f"      {result.error}", err=True)


@click.command("download", hidden=True)
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
@click.option("--make-playlist", is_flag=True, default=None, help="Create a local folder mirroring the Spotify playlist.")
@click.pass_context
def download(ctx: click.Context, url: str, **kwargs) -> None:
    parent = ctx.parent.params if ctx.parent else {}
    options = {**parent, **{key: value for key, value in kwargs.items() if value is not None}}
    options.setdefault("skip_existing", True)
    options.setdefault("dry_run", False)
    options.setdefault("verbose", False)
    options.setdefault("youtube_link", None)
    options.setdefault("make_playlist", False)
    run_download(url, options)


def register_download_command(cli: click.Group) -> None:
    cli.add_command(download)
