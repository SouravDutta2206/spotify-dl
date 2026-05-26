from __future__ import annotations

from datetime import datetime, timezone

from spotipy.oauth2 import SpotifyOAuth

from spotify_dl.config import ConfigManager
from spotify_dl.models import AppConfig

USER_SCOPES = "playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private"


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
        oauth = build_spotify_oauth(self.config, open_browser=True)
        token_info = oauth.get_access_token(as_dict=True, check_cache=False)
        expiry = datetime.fromtimestamp(token_info["expires_at"], tz=timezone.utc)
        self.config_manager.save_user_auth(
            access_token=token_info["access_token"],
            refresh_token=token_info.get("refresh_token"),
            token_expiry=expiry,
            scope=token_info.get("scope") or USER_SCOPES,
        )
        return "Logged in with Spotify user authentication."

    def logout(self) -> None:
        self.config_manager.clear_user_auth()
