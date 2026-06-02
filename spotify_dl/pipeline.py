from __future__ import annotations

import os
import shutil
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from spotify_dl.cli_utils import normalize_download_options, spotify_client_from_options
from spotify_dl.cover_art import CoverResolver
from spotify_dl.exceptions import SpotifyDlError, SpotifyError
from spotify_dl.filesystem import FileSystem
from spotify_dl.models import AppConfig, DownloadResult, TrackMetadata
from spotify_dl.source_cache import CoverCache
from spotify_dl.spotify import SpotifyClient, parse_spotify_url
from spotify_dl.tagger import Tagger
from spotify_dl.youtube import Downloader, YouTubeSearcher, make_direct_match


COLLECTION_MAX_WORKERS = 10
COLLECTION_SOURCE_TYPES = {"album", "playlist"}


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
            return DownloadResult(track, None, final_path, "skipped", None)
        if dry_run:
            return DownloadResult(track, None, final_path, "skipped", None)
        try:
            match = make_direct_match(youtube_url) if youtube_url else self.searcher.find_best_match(track)
            temp_path = self.downloader.download_mp3(match)
            tagged = self.tagger.tag(temp_path, final_path, track)
            if temp_path.parent.exists():
                shutil.rmtree(temp_path.parent, ignore_errors=True)
            self._copy_to_playlist(tagged, track)
            return DownloadResult(track, match, tagged, "done", None)
        except Exception as exc:
            return DownloadResult(track, None, final_path, "failed", str(exc))

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
    download_options = normalize_download_options(options)
    config, spotify = spotify_client_from_options(download_options)
    youtube_link = download_options.get("youtube_link")
    source_type, source_name, tracks = spotify.resolve_url(url)

    if source_type == "track" and tracks:
        track = tracks[0]
        if youtube_link:
            spotify.source_cache.write_track(track, youtube_link=youtube_link)
        else:
            cached = spotify.source_cache.read_track(track.spotify_id)
            youtube_link = cached[1] if cached else None
            download_options["youtube_link"] = youtube_link

    if source_type in COLLECTION_SOURCE_TYPES:
        CoverResolver(spotify.cover_cache).prefetch(tracks)

    download_tracks(
        config=config,
        source_type=source_type,
        source_name=source_name,
        tracks=tracks,
        options=download_options,
        cover_cache=spotify.cover_cache,
    )


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
    print(f"\n  {source_type.title()}: {source_name}")
    print(f"  Tracks: {len(tracks)}\n")
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
    print(f"\n  Done. {done} downloaded, {skipped} skipped, {failed} failed.")
    print(f"  Output: {config.output_directory}")


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

    if source_type not in COLLECTION_SOURCE_TYPES or options["dry_run"] or len(tracks) <= 1:
        results = []
        try:
            for index, track in enumerate(tracks, start=1):
                result = pipeline.process_track(
                    track,
                    skip_existing=options["skip_existing"],
                    dry_run=options["dry_run"],
                    youtube_url=youtube_link,
                )
                results.append(result)
                print_track_result(index, len(tracks), result)
        except KeyboardInterrupt:
            print("\n  Aborted.")
            raise SystemExit(130)
        return results

    workers = min(max(1, int(config.concurrency)), COLLECTION_MAX_WORKERS, len(tracks))
    print(f"  Processing {source_type} with {workers} concurrent workers.\n")
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
        futures_list = list(futures.keys())
        while futures_list:
            for future in [f for f in futures_list if f.done()]:
                completed += 1
                result = future.result()
                results.append(result)
                print_track_result(completed, len(tracks), result)
                futures_list.remove(future)
            if futures_list:
                time.sleep(0.05)
    except KeyboardInterrupt:
        for future in futures:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        print("\n  Aborted.")
        os._exit(130)
    else:
        executor.shutdown(wait=True)
    return results


def print_track_result(index: int, total: int, result: DownloadResult) -> None:
    """Print a single track's outcome to stdout (and errors to stderr)."""
    marker = result.status
    print(f"  [{index}/{total}] {result.track.title} ... {marker}")
    if result.error:
        print(f"      {result.error}", file=sys.stderr)
