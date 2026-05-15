from __future__ import annotations

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
