from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Literal

from yt_dlp import YoutubeDL

from spotify_dl.exceptions import DownloadError, YouTubeMatchError
from spotify_dl.models import AppConfig, TrackMetadata, YouTubeMatch

YtDlpMode = Literal["search", "download"]
_YT_VIDEO_ID_RE = re.compile(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})")


def javascript_runtime_options() -> dict[str, dict[str, str]]:
    if deno_path := shutil.which("deno"):
        return {"deno": {"path": deno_path}}
    if node_path := shutil.which("node"):
        return {"node": {"path": node_path}}
    return {}


def parse_cookies_from_browser(value: str) -> tuple[str, str | None, str | None, str | None]:
    browser_and_keyring, _, remainder = value.partition(":")
    browser, _, keyring = browser_and_keyring.partition("+")
    profile: str | None = None
    container: str | None = None
    if remainder:
        profile, separator, container_value = remainder.partition("::")
        container = container_value if separator else None
    return browser, profile or None, keyring or None, container


def cookie_options(config: AppConfig | None) -> dict[str, object]:
    if not config:
        return {}
    if config.youtube_cookie_file and config.youtube_cookie_file.exists():
        return {"cookiefile": str(config.youtube_cookie_file)}
    if config.youtube_cookie_browser:
        return {"cookiesfrombrowser": parse_cookies_from_browser(config.youtube_cookie_browser)}
    return {}


def parse_youtube_video_id(url: str) -> str:
    match = _YT_VIDEO_ID_RE.search(url)
    return match.group(1) if match else ""


def make_direct_match(url: str) -> YouTubeMatch:
    return YouTubeMatch(
        youtube_url=url,
        video_id=parse_youtube_video_id(url),
        video_title="",
        duration_seconds=0,
        match_score=-1,
        search_query="",
    )


def build_yt_dlp_options(
    *,
    mode: YtDlpMode,
    config: AppConfig | None = None,
    verbose: bool = False,
    output_template: str | None = None,
) -> dict[str, object]:
    options: dict[str, object] = {
        "quiet": not verbose,
        "no_warnings": not verbose,
    }
    if js_runtimes := javascript_runtime_options():
        options["js_runtimes"] = js_runtimes

    if mode == "search":
        options.update(
            {
                "skip_download": True,
                "extract_flat": False,
            }
        )
        options.update(cookie_options(config))
        return options

    if not config:
        raise ValueError("config is required for yt-dlp download options")
    if not output_template:
        raise ValueError("output_template is required for yt-dlp download options")

    postprocessor: dict[str, object] = {"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}
    if config.audio_quality != "0":
        postprocessor["preferredquality"] = config.audio_quality
    options.update(
        {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "noplaylist": True,
            "postprocessors": [postprocessor],
        }
    )
    options.update(cookie_options(config))
    return options


class YouTubeSearcher:
    def __init__(self, *, min_score: int = 65, verbose: bool = False) -> None:
        self.min_score = min_score
        self.verbose = verbose

    def build_query(self, track: TrackMetadata) -> str:
        return f"{track.artists[0]} - {track.title} lyrics"

    def find_best_match(self, track: TrackMetadata) -> YouTubeMatch:
        query = self.build_query(track)
        options = build_yt_dlp_options(mode="search", verbose=self.verbose)
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


class Downloader:
    def __init__(self, config: AppConfig, *, verbose: bool = False) -> None:
        self.config = config
        self.verbose = verbose

    def check_ffmpeg(self) -> None:
        if shutil.which("ffmpeg") is None:
            raise DownloadError("ffmpeg not found. Install ffmpeg and ensure it's in your PATH.")

    def download_mp3(self, match: YouTubeMatch) -> Path:
        self.check_ffmpeg()
        temp_dir = Path(tempfile.mkdtemp(prefix="spotify-dl-"))
        try:
            output_template = str(temp_dir / "%(id)s.%(ext)s")
            options = build_yt_dlp_options(
                mode="download",
                config=self.config,
                verbose=self.verbose,
                output_template=output_template,
            )
            try:
                with YoutubeDL(options) as ydl:
                    ydl.download([match.youtube_url])
            except Exception as exc:
                message = str(exc)
                if "age" in message.lower() and not (
                    self.config.youtube_cookie_file or self.config.youtube_cookie_browser
                ):
                    message += "\nTip: spotify-dl config set youtube-cookies-from chrome"
                raise DownloadError(f"Download failed: {message}") from exc
            files = list(temp_dir.glob("*.mp3"))
            if not files:
                raise DownloadError("Download failed: yt-dlp did not produce an MP3")
            return files[0]
        except Exception:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise
