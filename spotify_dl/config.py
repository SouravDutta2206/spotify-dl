from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from spotify_dl.exceptions import ConfigError
from spotify_dl.json_io import read_json, write_json_atomic
from spotify_dl.logging import get_logger
from spotify_dl.models import AppConfig

logger = get_logger("config")

CONFIG_HOME = Path.home() / ".spotify-dl"
CONFIG_PATH = CONFIG_HOME / "config.json"
VALID_QUALITIES = {"0", "128", "192", "320"}
VALID_BROWSERS = {
    "brave",
    "chrome",
    "chromium",
    "edge",
    "firefox",
    "opera",
    "safari",
    "vivaldi",
    "whale",
}


DEFAULT_CONFIG: dict[str, Any] = {
    "spotify": {
        "client_id": None,
        "client_secret": None,
        "user_auth": {
            "access_token": None,
            "refresh_token": None,
            "token_expiry": None,
            "scope": None,
            "display_name": None,
        },
    },
    "output": {"directory": "~/Music/spotify-dl", "quality": "0"},
    "youtube": {"cookie_browser": None, "cookie_file": None},
    "auth": {"callback_port": 8888},
    "concurrency": 5,
}


def _deep_merge(base: dict[str, Any], partial: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in partial.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _expand_path(value: str | None) -> Path | None:
    if not value:
        return None
    return Path(value).expanduser()


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _cookie_browser_name(value: str) -> str:
    return value.split("+", 1)[0].split(":", 1)[0].lower()


class ConfigManager:
    def __init__(self, config_path: Path = CONFIG_PATH) -> None:
        self.config_path = config_path

    def read_raw(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return deepcopy(DEFAULT_CONFIG)
        try:
            loaded = read_json(self.config_path)
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Config file is not valid JSON: {self.config_path}") from exc
        return _deep_merge(DEFAULT_CONFIG, loaded)

    def load(
        self,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
        output_directory: str | Path | None = None,
        quality: str | None = None,
        youtube_cookie_browser: str | None = None,
        youtube_cookie_file: str | Path | None = None,
        concurrency: int | None = None,
        require_credentials: bool = True,
    ) -> AppConfig:
        load_dotenv()
        raw = self.read_raw()
        logger.debug("Config loaded from %s", self.config_path)
        spotify = raw["spotify"]
        user_auth = spotify["user_auth"]

        resolved_client_id = client_id or os.getenv("SPOTIFY_CLIENT_ID") or spotify.get("client_id")
        resolved_client_secret = (
            client_secret or os.getenv("SPOTIFY_CLIENT_SECRET") or spotify.get("client_secret")
        )
        if require_credentials and (not resolved_client_id or not resolved_client_secret):
            raise ConfigError(
                "Spotify API credentials not found.\n\n"
                "Run:  spotify-dl config set client-id <id>\n"
                "      spotify-dl config set client-secret <secret>\n"
                "  or: set SPOTIFY_CLIENT_ID=<id> and SPOTIFY_CLIENT_SECRET=<secret>\n\n"
                "Get your credentials at: https://developer.spotify.com/dashboard"
            )

        logger.debug("Resolved output directory: %s",
                     Path(output_directory).expanduser() if output_directory else Path(raw['output']['directory']).expanduser())

        resolved_quality = str(quality or raw["output"]["quality"])
        if resolved_quality not in VALID_QUALITIES:
            raise ConfigError("Audio quality must be one of: 0, 128, 192, 320")

        browser = youtube_cookie_browser or raw["youtube"].get("cookie_browser")
        if browser and _cookie_browser_name(browser) not in VALID_BROWSERS:
            browser = None

        cookie_file = youtube_cookie_file or raw["youtube"].get("cookie_file")
        return AppConfig(
            spotify_client_id=resolved_client_id or "",
            spotify_client_secret=resolved_client_secret or "",
            spotify_user_access_token=user_auth.get("access_token"),
            spotify_user_refresh_token=user_auth.get("refresh_token"),
            spotify_user_token_expiry=_parse_datetime(user_auth.get("token_expiry")),
            output_directory=Path(output_directory).expanduser()
            if output_directory
            else Path(raw["output"]["directory"]).expanduser(),
            audio_quality=resolved_quality,
            youtube_cookie_browser=browser,
            youtube_cookie_file=_expand_path(str(cookie_file)) if cookie_file else None,
            auth_callback_port=int(raw["auth"]["callback_port"]),
            concurrency=int(concurrency or raw.get("concurrency") or 5),
        )

    def save(self, partial: dict[str, Any]) -> None:
        current = self.read_raw()
        next_config = _deep_merge(current, partial)
        write_json_atomic(self.config_path, next_config)
        logger.info("Config saved to %s", self.config_path)

    def clear(self) -> None:
        if self.config_path.exists():
            self.config_path.unlink()
        logger.info("Config cleared")

    def clear_cookies(self) -> None:
        self.save({"youtube": {"cookie_browser": None, "cookie_file": None}})

    def save_user_auth(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
        token_expiry: datetime,
        scope: str | None,
    ) -> None:
        self.save(
            {
                "spotify": {
                    "user_auth": {
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "token_expiry": token_expiry.isoformat().replace("+00:00", "Z"),
                        "scope": scope,
                    }
                }
            }
        )

    def clear_user_auth(self) -> None:
        self.save(
            {
                "spotify": {
                    "user_auth": {
                        "access_token": None,
                        "refresh_token": None,
                        "token_expiry": None,
                        "scope": None,
                        "display_name": None,
                    }
                }
            }
        )

    def masked(self) -> dict[str, Any]:
        raw = self.read_raw()
        secret = raw["spotify"].get("client_secret")
        if secret:
            raw["spotify"]["client_secret"] = f"{secret[:4]}****"
        return raw
