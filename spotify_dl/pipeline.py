from __future__ import annotations

import shutil
from pathlib import Path

from spotify_dl.filesystem import FileSystem, sanitize_component
from spotify_dl.models import AppConfig, DownloadResult, TrackMetadata
from spotify_dl.source_cache import CoverCache
from spotify_dl.tagger import Tagger
from spotify_dl.youtube import Downloader, YouTubeSearcher, make_direct_match


class DownloadPipeline:
    def __init__(
        self,
        config: AppConfig,
        *,
        cover_cache: CoverCache | None = None,
        verbose: bool = False,
        playlist_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.filesystem = FileSystem(config.output_directory)
        self.searcher = YouTubeSearcher(verbose=verbose)
        self.downloader = Downloader(config, verbose=verbose)
        self.tagger = Tagger(cover_cache=cover_cache)
        self.playlist_dir = playlist_dir

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
        if not self.playlist_dir:
            return
        self.playlist_dir.mkdir(parents=True, exist_ok=True)
        title = sanitize_component(track.title)
        dest = self.playlist_dir / f"{title}.mp3"
        shutil.copy2(source, dest)
