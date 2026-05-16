from __future__ import annotations

from datetime import datetime, timezone

from spotify_dl.config import ConfigManager


def test_config_save_load_and_mask(tmp_path, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    manager = ConfigManager(tmp_path / "config.json")

    manager.save(
        {
            "spotify": {"client_id": "abc", "client_secret": "def456"},
            "output": {"directory": str(tmp_path / "music"), "quality": "320"},
            "youtube": {"cookie_browser": "chrome"},
        }
    )

    config = manager.load()

    assert config.spotify_client_id == "abc"
    assert config.spotify_client_secret == "def456"
    assert config.output_directory == tmp_path / "music"
    assert config.audio_quality == "320"
    assert config.youtube_cookie_browser == "chrome"
    assert manager.masked()["spotify"]["client_secret"] == "def4****"


def test_env_credentials_override_file(tmp_path, monkeypatch):
    manager = ConfigManager(tmp_path / "config.json")
    manager.save({"spotify": {"client_id": "file-id", "client_secret": "file-secret"}})
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "env-id")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "env-secret")

    config = manager.load()

    assert config.spotify_client_id == "env-id"
    assert config.spotify_client_secret == "env-secret"


def test_cookie_browser_accepts_profile_spec(tmp_path, monkeypatch):
    monkeypatch.delenv("SPOTIFY_CLIENT_ID", raising=False)
    monkeypatch.delenv("SPOTIFY_CLIENT_SECRET", raising=False)
    manager = ConfigManager(tmp_path / "config.json")
    browser = r"firefox:C:\Users\soura\AppData\Roaming\zen\Profiles\abc.Default"
    manager.save(
        {
            "spotify": {"client_id": "abc", "client_secret": "def456"},
            "youtube": {"cookie_browser": browser},
        }
    )

    assert manager.load().youtube_cookie_browser == browser


def test_save_and_clear_user_auth(tmp_path):
    manager = ConfigManager(tmp_path / "config.json")
    expiry = datetime(2026, 1, 1, tzinfo=timezone.utc)

    manager.save_user_auth(
        access_token="access",
        refresh_token="refresh",
        token_expiry=expiry,
        scope="playlist-read-private",
    )

    raw = manager.read_raw()
    assert raw["spotify"]["user_auth"]["access_token"] == "access"
    assert raw["spotify"]["user_auth"]["refresh_token"] == "refresh"
    assert raw["spotify"]["user_auth"]["token_expiry"] == "2026-01-01T00:00:00Z"
    assert raw["spotify"]["user_auth"]["scope"] == "playlist-read-private"

    manager.clear_user_auth()

    raw = manager.read_raw()
    assert raw["spotify"]["user_auth"]["access_token"] is None
    assert raw["spotify"]["user_auth"]["refresh_token"] is None
    assert raw["spotify"]["user_auth"]["token_expiry"] is None
    assert raw["spotify"]["user_auth"]["scope"] is None
