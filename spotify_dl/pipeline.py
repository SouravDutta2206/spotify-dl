from __future__ import annotations

import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import click

from spotify_dl.filesystem import FileSystem
from spotify_dl.models import AppConfig, DownloadResult, TrackMetadata
from spotify_dl.source_cache import CoverCache
from spotify_dl.tagger import Tagger
from spotify_dl.youtube import Downloader, YouTubeSearcher, make_direct_match

COLLECTION_MAX_WORKERS = 10
CONCURRENT_SOURCE_TYPES = {"album", "playlist"}


class DownloadPipeline:
    def __init__(
        self,
        config: AppConfig,
        *,
        cover_cache: CoverCache | None = None,
        verbose: bool = False,
        playlist_name: str | None = None,
    ) -> None:
        self.config = config
        self.filesystem = FileSystem(config.output_directory)
        self.searcher = YouTubeSearcher(verbose=verbose)
        self.downloader = Downloader(config, verbose=verbose)
        self.tagger = Tagger(cover_cache=cover_cache)
        self.playlist_name = playlist_name

    def process_track(
        self,
        track: TrackMetadata,
        *,
        skip_existing: bool = True,
        dry_run: bool = False,
        youtube_url: str | None = None,
    ) -> DownloadResult:
        final_path = self.filesystem.get_track_path(track)
        if skip_existing and final_path.exists():
            self._copy_to_playlist(final_path, track)
            return DownloadResult(track, None, None, final_path, "skipped", None)
        if dry_run:
            return DownloadResult(track, None, None, final_path, "skipped", None)
        try:
            match = make_direct_match(youtube_url) if youtube_url else self.searcher.find_best_match(track)
            temp_path = self.downloader.download_mp3(match)
            tagged = self.tagger.tag(temp_path, final_path, track)
            self._copy_to_playlist(tagged, track)
            return DownloadResult(track, match, None, tagged, "done", None)
        except Exception as exc:
            return DownloadResult(track, None, None, final_path, "failed", str(exc))

    def _copy_to_playlist(self, source: Path, track: TrackMetadata) -> None:
        if not self.playlist_name:
            return
        dest = self.filesystem.get_playlist_mirror_path(track, self.playlist_name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)


# ---------------------------------------------------------------------------
# Orchestration layer
# ---------------------------------------------------------------------------


def run_download(url: str, options: dict) -> None:
    """Resolve a Spotify URL and download all tracks."""
    from spotify_dl.commands.common import (  # local import avoids circular dep
        spotify_client_from_options,
    )
    from spotify_dl.exceptions import SpotifyDlError

    try:
        config, spotify = spotify_client_from_options(options)
        source_type, source_name, tracks = spotify.resolve_url(url)
        youtube_link = options.get("youtube_link")
        if youtube_link and source_type != "track":
            raise click.ClickException("--youtube-link can only be used with a single Spotify track URL.")
        download_tracks(
            config=config,
            source_type=source_type,
            source_name=source_name,
            tracks=tracks,
            options=options,
            cover_cache=spotify.cover_cache,
        )
    except SpotifyDlError as exc:
        from spotify_dl.commands.common import handle_spotify_dl_error
        raise handle_spotify_dl_error(exc) from exc


def download_tracks(
    *,
    config: AppConfig,
    source_type: str,
    source_name: str,
    tracks: list[TrackMetadata],
    options: dict,
    cover_cache: CoverCache | None = None,
) -> None:
    """Print source header, dispatch to process_tracks, print summary."""
    click.echo(f"\n  {source_type.title()}: {source_name}")
    click.echo(f"  Tracks: {len(tracks)}\n")
    make_playlist = options.get("make_playlist", False)
    playlist_name = source_name if make_playlist and source_type == "playlist" else None
    results = process_tracks(
        config=config,
        source_type=source_type,
        tracks=tracks,
        options=options,
        cover_cache=cover_cache,
        youtube_link=options.get("youtube_link"),
        playlist_name=playlist_name,
    )
    done = sum(1 for result in results if result.status == "done")
    skipped = sum(1 for result in results if result.status == "skipped")
    failed = sum(1 for result in results if result.status == "failed")
    click.echo(f"\n  Done. {done} downloaded, {skipped} skipped, {failed} failed.")
    click.echo(f"  Output: {config.output_directory}")


def process_tracks(
    *,
    config: AppConfig,
    source_type: str,
    tracks: list[TrackMetadata],
    options: dict,
    cover_cache: CoverCache | None = None,
    youtube_link: str | None = None,
    playlist_name: str | None = None,
) -> list[DownloadResult]:
    """Run sequential or concurrent download based on source type and options."""
    pipeline = DownloadPipeline(
        config,
        cover_cache=cover_cache,
        verbose=options["verbose"],
        playlist_name=playlist_name,
    )

    if source_type not in CONCURRENT_SOURCE_TYPES or options["dry_run"] or len(tracks) <= 1:
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
    results: list[DownloadResult] = []
    completed = 0
    executor = ThreadPoolExecutor(max_workers=workers)
    futures = {
        executor.submit(
            pipeline.process_track,
            track,
            skip_existing=options["skip_existing"],
            dry_run=options["dry_run"],
            youtube_url=youtube_link,
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
        raise SystemExit(130)
    else:
        executor.shutdown(wait=True)
    return results


def print_track_result(index: int, total: int, result: DownloadResult) -> None:
    """Print a single track's outcome to stdout (and errors to stderr)."""
    marker = {"done": "done", "skipped": "skipped", "failed": "failed"}[result.status]
    click.echo(f"  [{index}/{total}] {result.track.title} ... {marker}")
    if result.error:
        click.echo(f"      {result.error}", err=True)

