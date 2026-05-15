from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from yt_dlp import YoutubeDL

from spotify_dl.exceptions import DownloadError
from spotify_dl.models import AppConfig, YouTubeMatch
from spotify_dl.yt_dlp_options import javascript_runtime_options


def parse_cookies_from_browser(value: str) -> tuple[str, str | None, str | None, str | None]:
    browser_and_keyring, _, remainder = value.partition(":")
    browser, _, keyring = browser_and_keyring.partition("+")
    profile: str | None = None
    container: str | None = None
    if remainder:
        profile, separator, container_value = remainder.partition("::")
        container = container_value if separator else None
    return browser, profile or None, keyring or None, container


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
        output_template = str(temp_dir / "%(id)s.%(ext)s")
        options: dict[str, object] = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "quiet": not self.verbose,
            "no_warnings": not self.verbose,
            "noplaylist": True,
            "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3"}],
        }
        if js_runtimes := javascript_runtime_options():
            options["js_runtimes"] = js_runtimes
        if self.config.audio_quality != "0":
            options["postprocessors"][0]["preferredquality"] = self.config.audio_quality  # type: ignore[index]
        if self.config.youtube_cookie_file and self.config.youtube_cookie_file.exists():
            options["cookiefile"] = str(self.config.youtube_cookie_file)
        elif self.config.youtube_cookie_browser:
            options["cookiesfrombrowser"] = parse_cookies_from_browser(
                self.config.youtube_cookie_browser
            )
        try:
            with YoutubeDL(options) as ydl:
                ydl.download([match.youtube_url])
        except Exception as exc:
            message = str(exc)
            if "age" in message.lower() and not (
                self.config.youtube_cookie_file or self.config.youtube_cookie_browser
            ):
                message += "\nTip: spotify-dl config set --youtube-cookies-from chrome"
            raise DownloadError(f"Download failed: {message}") from exc
        files = list(temp_dir.glob("*.mp3"))
        if not files:
            raise DownloadError("Download failed: yt-dlp did not produce an MP3")
        return files[0]
