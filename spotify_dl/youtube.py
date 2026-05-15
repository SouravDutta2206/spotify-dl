from __future__ import annotations

from yt_dlp import YoutubeDL

from spotify_dl.exceptions import YouTubeMatchError
from spotify_dl.models import TrackMetadata, YouTubeMatch
from spotify_dl.yt_dlp_options import javascript_runtime_options


class YouTubeSearcher:
    def __init__(self, *, min_score: int = 65, verbose: bool = False) -> None:
        self.min_score = min_score
        self.verbose = verbose

    def build_query(self, track: TrackMetadata) -> str:
        return f"{track.artists[0]} - {track.title} audio"

    def find_best_match(self, track: TrackMetadata) -> YouTubeMatch:
        query = self.build_query(track)
        options = {
            "quiet": not self.verbose,
            "no_warnings": not self.verbose,
            "skip_download": True,
            "extract_flat": False,
        }
        if js_runtimes := javascript_runtime_options():
            options["js_runtimes"] = js_runtimes
        with YoutubeDL(options) as ydl:
            data = ydl.extract_info(f"ytsearch10:{query}", download=False)
        entries = (data or {}).get("entries") or []
        candidates = [self._score(entry, track, query) for entry in entries if entry]
        candidates = [candidate for candidate in candidates if candidate.match_score >= self.min_score]
        if not candidates:
            raise YouTubeMatchError("No matching YouTube video found")
        return max(candidates, key=lambda candidate: candidate.match_score)

    def _score(self, entry: dict, track: TrackMetadata, query: str) -> YouTubeMatch:
        duration = int(entry.get("duration") or 0)
        expected = max(1, round(track.duration_ms / 1000))
        delta = abs(duration - expected)
        duration_score = max(0, 100 - delta * 4)
        title = (entry.get("title") or "").lower()
        text_score = 0
        if track.title.lower() in title:
            text_score += 20
        if track.artists and track.artists[0].lower() in title:
            text_score += 20
        score = min(100, int(duration_score * 0.7 + text_score))
        video_id = entry.get("id") or ""
        return YouTubeMatch(
            youtube_url=entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
            video_id=video_id,
            video_title=entry.get("title") or "",
            duration_seconds=duration,
            match_score=score,
            search_query=query,
        )
