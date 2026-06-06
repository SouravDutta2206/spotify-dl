from __future__ import annotations

from datetime import datetime, timezone

from spotipy.oauth2 import SpotifyOAuth

from spotify_dl.config import ConfigManager
from spotify_dl.logging import get_logger
from spotify_dl.models import AppConfig

logger = get_logger("auth")

USER_SCOPES = (
    "playlist-read-private playlist-read-collaborative "
    "playlist-modify-public playlist-modify-private "
    "user-read-private user-read-email"
)


def build_spotify_oauth(config: AppConfig, *, open_browser: bool) -> SpotifyOAuth:
    """Construct a SpotifyOAuth instance from app config."""
    return SpotifyOAuth(
        client_id=config.spotify_client_id,
        client_secret=config.spotify_client_secret,
        redirect_uri=f"http://127.0.0.1:{config.auth_callback_port}/callback",
        scope=USER_SCOPES,
        open_browser=open_browser,
    )


class AuthManager:
    def __init__(self, config: AppConfig, config_manager: ConfigManager) -> None:
        self.config = config
        self.config_manager = config_manager

    def login(self) -> str:
        logger.info("Login attempt started")
        import os
        import sys

        # Fall back to headless authentication if no DISPLAY is set or requested via env var
        open_browser = True
        if os.getenv("SPOTIFY_DL_HEADLESS") == "1":
            open_browser = False
        elif sys.platform != "win32" and "DISPLAY" not in os.environ:
            open_browser = False

        oauth = build_spotify_oauth(self.config, open_browser=open_browser)
        token_info = oauth.get_access_token(as_dict=True, check_cache=False)
        expiry = datetime.fromtimestamp(token_info["expires_at"], tz=timezone.utc)
        self.config_manager.save_user_auth(
            access_token=token_info["access_token"],
            refresh_token=token_info.get("refresh_token"),
            token_expiry=expiry,
            scope=token_info.get("scope") or USER_SCOPES,
        )
        logger.info("Login successful")
        return "Logged in with Spotify user authentication."

    def logout(self) -> None:
        logger.info("Logout")
        self.config_manager.clear_user_auth()
