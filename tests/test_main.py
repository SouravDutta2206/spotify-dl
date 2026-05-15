from __future__ import annotations

import pytest

from spotify_dl.main import _process_tracks
from spotify_dl.models import AppConfig
from tests.test_filesystem import make_track


def test_concurrent_playlist_processing_aborts_on_keyboard_interrupt(tmp_path, monkeypatch):
    config = AppConfig(
        spotify_client_id="id",
        spotify_client_secret="secret",
        spotify_user_access_token=None,
        spotify_user_refresh_token=None,
        spotify_user_token_expiry=None,
        output_directory=tmp_path,
        audio_quality="0",
        youtube_cookie_browser=None,
        youtube_cookie_file=None,
        auth_callback_port=8888,
        concurrency=5,
    )

    class FakeFuture:
        def cancel(self):
            return True

        def result(self):
            raise AssertionError("result should not be called")

    class FakeExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers
            self.shutdown_args = None

        def submit(self, *args, **kwargs):
            return FakeFuture()

        def shutdown(self, **kwargs):
            self.shutdown_args = kwargs

    executor = FakeExecutor(max_workers=5)
    exit_codes = []
    monkeypatch.setattr("spotify_dl.main.ThreadPoolExecutor", lambda max_workers: executor)
    monkeypatch.setattr("spotify_dl.main.as_completed", lambda futures: (_ for _ in ()).throw(KeyboardInterrupt))
    monkeypatch.setattr(
        "spotify_dl.main.os._exit",
        lambda code: exit_codes.append(code) or (_ for _ in ()).throw(SystemExit(code)),
    )

    with pytest.raises(SystemExit):
        _process_tracks(
            config=config,
            source_type="playlist",
            tracks=[make_track(spotify_id=str(index)) for index in range(2)],
            options={"skip_existing": True, "dry_run": False, "verbose": False},
        )

    assert executor.shutdown_args == {"wait": False, "cancel_futures": True}
    assert exit_codes == [130]
