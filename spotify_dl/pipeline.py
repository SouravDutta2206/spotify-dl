from __future__ import annotations

import re

from spotify_dl.downloader import Downloader
from spotify_dl.filesystem import FileSystem
from spotify_dl.models import AppConfig, DownloadResult, TrackMetadata, YouTubeMatch
from spotify_dl.source_cache import CoverCache
from spotify_dl.tagger import Tagger
from spotify_dl.youtube import YouTubeSearcher

_YT_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})")


class DownloadPipeline:
    def __init__(
        self,
        config: AppConfig,
        *,
        cover_cache: CoverCache | None = None,
        verbose: bool = False,
    ) -> None:
        self.config = config
        self.filesystem = FileSystem(config.output_directory)
        self.searcher = YouTubeSearcher(verbose=verbose)
        self.downloader = Downloader(config, verbose=verbose)
        self.tagger = Tagger(cover_cache=cover_cache)

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
            return DownloadResult(track, None, None, final_path, "skipped", None)
        if dry_run:
            return DownloadResult(track, None, None, final_path, "skipped", None)
        try:
            if youtube_url:
                m = _YT_VIDEO_ID_RE.search(youtube_url)
                match = YouTubeMatch(
                    youtube_url=youtube_url,
                    video_id=m.group(1) if m else "",
                    video_title="",
                    duration_seconds=0,
                    match_score=-1,
                    search_query="",
                )
            else:
                match = self.searcher.find_best_match(track)
            temp_path = self.downloader.download_mp3(match)
            tagged = self.tagger.tag(temp_path, final_path, track)
            return DownloadResult(track, match, None, tagged, "done", None)
        except Exception as exc:
            return DownloadResult(track, None, None, final_path, "failed", str(exc))
