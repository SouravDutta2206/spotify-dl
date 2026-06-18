from __future__ import annotations

import logging
import os
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from spotify_dl.cli_utils import spotify_client_from_options
from spotify_dl.cover_art import CoverResolver
from spotify_dl.exceptions import SpotifyError
from spotify_dl.filesystem import FileSystem
from spotify_dl.logging import get_logger
from spotify_dl.models import AppConfig, DownloadOptions, DownloadResult, TrackMetadata, YouTubeMatch
from spotify_dl.progress import ProgressBar
from spotify_dl.source_cache import CoverCache, SourceCache
from spotify_dl.spotify import parse_spotify_url
from spotify_dl.tagger import Tagger
from spotify_dl.youtube import Downloader, YouTubeSearcher, make_direct_match

logger = get_logger("pipeline")
_failed_logger = logging.getLogger("spotify_dl.failed")


COLLECTION_MAX_WORKERS = 10
COLLECTION_SOURCE_TYPES = {"album", "playlist"}


class DownloadPipeline:
    def __init__(
        self,
        config: AppConfig,
        options: DownloadOptions,
        *,
        cover_cache: CoverCache | None = None,
        source_cache: SourceCache | None = None,
    ) -> None:
        self.config = config
        self.options = options
        self.skip_existing = options.skip_existing
        self.dry_run = options.dry_run
        self.youtube_link = options.youtube_link
        self.youtube_link_map = options.youtube_link_map or {}
        self.source_cache = source_cache
        self.filesystem = FileSystem(config.output_directory)
        self.searcher = YouTubeSearcher(config=config, verbose=options.verbose)
        self.downloader = Downloader(config, verbose=options.verbose)
        self.tagger = Tagger(cover_cache=cover_cache)
        self.playlist_name: str | None = None

    def persist_youtube_links(
        self,
        tracks: list[TrackMetadata],
        *,
        youtube_link: str | None = None,
        youtube_link_map: dict[str, str | None] | None = None,
    ) -> None:
        if not self.source_cache:
            return
        wrote_cache = False
        for track in tracks:
            link = youtube_link or (youtube_link_map or {}).get(track.spotify_id)
            if not link:
                continue
            self.source_cache.write_track(track, youtube_link=link)
            wrote_cache = True
        if wrote_cache:
            self.source_cache.flush_tracks()

    def download_source(
        self,
        *,
        source_type: str,
        source_name: str,
        tracks: list[TrackMetadata],
    ) -> None:
        logger.info("%s: %s — %d track(s)", source_type.title(), source_name, len(tracks))
        print(f"\n  {source_type.title()}: {source_name}")
        print(f"  Tracks: {len(tracks)}\n")
        make_playlist = self.options.make_playlist
        self.playlist_name = source_name if make_playlist and source_type == "playlist" else None

        results = self._process_tracks(source_type=source_type, tracks=tracks)
        done = sum(1 for result in results if result.status == "done")
        skipped = sum(1 for result in results if result.status == "skipped")
        failed_results = [r for r in results if r.status == "failed"]
        logger.info("Summary: %d downloaded, %d skipped, %d failed", done, skipped, len(failed_results))
        print(f"\n  Done. {done} downloaded, {skipped} skipped, {len(failed_results)} failed.")
        print(f"  Output: {self.config.output_directory}")

        if failed_results:
            print("\n  Failed tracks:")
            for result in failed_results:
                artist = result.track.artists[0] if result.track.artists else "Unknown"
                _failed_logger.info("%s - %s | %s", artist, result.track.title, result.error)
                print(f"    \u2022 {artist} - {result.track.title}: {result.error}")

    def process_track(
        self,
        track: TrackMetadata,
        *,
        youtube_match: YouTubeMatch | None = None,
    ) -> DownloadResult:
        label = f"\"{track.title}\" by {track.artists[0]} ({track.spotify_id})"
        final_path = self.filesystem.get_track_path(track)
        if self.skip_existing and self.filesystem.exists(track):
            logger.debug("Skipped (exists): %s", label)
            self._copy_to_playlist(final_path, track)
            return DownloadResult(track, None, final_path, "skipped", None)
        if self.dry_run:
            logger.debug("Skipped (dry run): %s", label)
            return DownloadResult(track, None, final_path, "skipped", None)
        try:
            logger.debug("Processing: %s", label)
            match = youtube_match or self.searcher.find_best_match(track)
            logger.info("Matched: %s -> %s (score=%d)", label, match.youtube_url, match.match_score)
            temp_path = self.downloader.download_mp3(match)
            tagged = self.tagger.tag(temp_path, final_path, track)
            if temp_path.parent.exists():
                shutil.rmtree(temp_path.parent, ignore_errors=True)
            self._copy_to_playlist(tagged, track)
            logger.info("Done: %s -> %s", label, tagged)
            return DownloadResult(track, match, tagged, "done", None)
        except Exception as exc:
            logger.error("Failed: %s — %s", label, exc)
            _failed_logger.info("%s - %s | %s", track.artists[0], track.title, exc)
            return DownloadResult(track, None, final_path, "failed", str(exc))

    def _resolve_youtube_matches(
        self,
        tracks: list[TrackMetadata],
    ) -> tuple[dict[str, YouTubeMatch], dict[str, str]]:
        resolved_matches: dict[str, YouTubeMatch] = {}
        failed_searches: dict[str, str] = {}
        tracks_to_search: list[TrackMetadata] = []

        for track in tracks:
            override = self.youtube_link_map.get(track.spotify_id) or self.youtube_link
            if override:
                resolved_matches[track.spotify_id] = make_direct_match(override)
                continue

            cached = self.source_cache.read_track(track.spotify_id) if self.source_cache else None
            if cached and cached[1]:
                resolved_matches[track.spotify_id] = make_direct_match(cached[1])
                continue

            tracks_to_search.append(track)

        if self.skip_existing:
            tracks_to_search = [track for track in tracks_to_search if not self.filesystem.exists(track)]

        if not tracks_to_search or self.dry_run:
            return resolved_matches, failed_searches

        with ProgressBar(len(tracks_to_search), "Searching YouTube", color="cyan", show_eta=False) as bar:
            for index, track in enumerate(tracks_to_search, start=1):
                label = f"{track.artists[0]} - {track.title}"
                try:
                    time.sleep(1.0)
                    match = self.searcher.find_best_match(track)
                    resolved_matches[track.spotify_id] = match
                    bar.log(f"  [{index}/{len(tracks_to_search)}] Matched: {label}")
                    bar.advance(label, status="found")
                    if self.source_cache:
                        self.source_cache.write_track(track, youtube_link=match.youtube_url)
                except Exception as exc:
                    logger.error("Search failed for %s: %s", label, exc)
                    bar.log(f"  [{index}/{len(tracks_to_search)}] Search failed: {label} — {exc}")
                    bar.advance(label, status="failed")
                    failed_searches[track.spotify_id] = str(exc)

        if self.source_cache:
            self.source_cache.flush_tracks()
        self.searcher.close()
        return resolved_matches, failed_searches

    def _process_or_fail(
        self,
        track: TrackMetadata,
        *,
        resolved_matches: dict[str, YouTubeMatch],
        failed_searches: dict[str, str],
    ) -> DownloadResult:
        if track.spotify_id in failed_searches:
            return DownloadResult(track, None, self.filesystem.get_track_path(track), "failed", failed_searches[track.spotify_id])
        return self.process_track(track, youtube_match=resolved_matches.get(track.spotify_id))

    def _process_tracks(
        self,
        *,
        source_type: str,
        tracks: list[TrackMetadata],
    ) -> list[DownloadResult]:
        resolved_matches, failed_searches = self._resolve_youtube_matches(tracks)

        if self.dry_run or len(tracks) <= 1:
            results = []
            try:
                with ProgressBar(len(tracks)) as bar:
                    for index, track in enumerate(tracks, start=1):
                        result = self._process_or_fail(
                            track,
                            resolved_matches=resolved_matches,
                            failed_searches=failed_searches,
                        )
                        results.append(result)
                        _log_track_result(bar, index, len(tracks), result)
                        bar.advance(_track_label(result.track), status=result.status)
            except KeyboardInterrupt:
                print("\n  Aborted.")
                raise SystemExit(130)
            return results

        workers = min(max(1, int(self.config.concurrency)), COLLECTION_MAX_WORKERS, len(tracks))
        logger.debug("Downloading %s with %d concurrent workers", source_type, workers)
        print(f"\n  Downloading {source_type} with {workers} concurrent workers.\n")
        results: list[DownloadResult] = []
        executor = ThreadPoolExecutor(max_workers=workers)
        futures: dict = {}
        for index, track in enumerate(tracks):
            future = executor.submit(
                self._process_or_fail,
                track,
                resolved_matches=resolved_matches,
                failed_searches=failed_searches,
            )
            futures[future] = track
            if (index + 1) % workers == 0 and (index + 1) < len(tracks):
                time.sleep(1.0)
        try:
            futures_list = list(futures.keys())
            completed = 0
            with ProgressBar(len(tracks)) as bar:
                while futures_list:
                    for future in [f for f in futures_list if f.done()]:
                        completed += 1
                        result = future.result()
                        results.append(result)
                        _log_track_result(bar, completed, len(tracks), result)
                        bar.advance(_track_label(result.track), status=result.status)
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

    def _copy_to_playlist(self, source: Path, track: TrackMetadata) -> None:
        if not self.playlist_name:
            return
        dest = self.filesystem.get_playlist_mirror_path(track, self.playlist_name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)


# ---------------------------------------------------------------------------
# Orchestration layer
# ---------------------------------------------------------------------------


def run_download(urls: str | list[str], options: DownloadOptions) -> None:
    """Resolve Spotify URL(s) and download all tracks."""
    config, spotify = spotify_client_from_options(options)
    pipeline = DownloadPipeline(
        config,
        options,
        cover_cache=spotify.cover_cache,
        source_cache=spotify.source_cache,
    )

    url_desc = f"{len(urls)} URL(s)" if isinstance(urls, list) else urls
    logger.info("run_download: %s, skip_existing=%s, quality=%s",
                url_desc, options.skip_existing, config.audio_quality)

    if isinstance(urls, list):
        # Batch track resolution
        source_type = "batch"
        track_ids = []
        for url in urls:
            _, track_id = parse_spotify_url(url)
            if track_id:
                track_ids.append(track_id)
        print(f"\n  Batch resolving {len(track_ids)} tracks...")
        logger.info("Batch resolving %d tracks", len(track_ids))
        try:
            tracks = spotify.batch_resolve_tracks(track_ids)
        except SpotifyError as exc:
            logger.warning("Batch resolve failed (%s), falling back to individual", exc)
            print(f"  Batch resolve failed ({exc}), falling back to individual resolution...")
            for url in urls:
                run_download(url, options)
            return
        source_name = f"Batch Download ({len(tracks)} tracks)"
        pipeline.persist_youtube_links(
            tracks,
            youtube_link_map=options.youtube_link_map or {},
        )
    else:
        # Single URL resolution
        source_type, source_name, tracks = spotify.resolve_url(urls)
        if source_type == "track" and tracks:
            pipeline.persist_youtube_links(
                tracks,
                youtube_link=options.youtube_link,
                youtube_link_map=options.youtube_link_map or {},
            )

    if len(tracks) > 1:
        CoverResolver(spotify.cover_cache).prefetch(tracks)

    pipeline.download_source(
        source_type=source_type,
        source_name=source_name,
        tracks=tracks,
    )


def _track_label(track: TrackMetadata) -> str:
    """Build a short display label for a track."""
    artist = track.artists[0] if track.artists else "Unknown"
    return f"{artist} - {track.title}"


def _log_track_result(bar: ProgressBar, index: int, total: int, result: DownloadResult) -> None:
    """Print a track's outcome above the progress bar."""
    marker = result.status
    bar.log(f"  [{index}/{total}] {result.track.title} ... {marker}")
    if result.error:
        bar.log(f"      {result.error}")
