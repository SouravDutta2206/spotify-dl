from __future__ import annotations

import pytest

from spotify_dl.pipeline import process_tracks
from spotify_dl.models import AppConfig, DownloadResult
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
    monkeypatch.setattr("spotify_dl.pipeline.ThreadPoolExecutor", lambda max_workers: executor)
    monkeypatch.setattr(
        "spotify_dl.pipeline.as_completed",
        lambda futures: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    with pytest.raises(SystemExit):
        process_tracks(
            config=config,
            source_type="playlist",
            tracks=[make_track(spotify_id=str(index)) for index in range(2)],
            options={"skip_existing": True, "dry_run": False, "verbose": False},
        )

    assert executor.shutdown_args == {"wait": False, "cancel_futures": True}


def test_album_processing_uses_concurrent_workers(tmp_path, monkeypatch):
    config = _app_config(tmp_path, concurrency=3)

    class FakeFuture:
        def __init__(self, result):
            self._result = result

        def result(self):
            return self._result

    class FakeExecutor:
        def __init__(self, max_workers):
            self.max_workers = max_workers
            self.submitted = []
            self.shutdown_args = None

        def submit(self, func, track, **kwargs):
            self.submitted.append((func, track, kwargs))
            return FakeFuture(DownloadResult(track, None, None, tmp_path / "out.mp3", "done", None))

        def shutdown(self, **kwargs):
            self.shutdown_args = kwargs

    executor = FakeExecutor(max_workers=3)
    monkeypatch.setattr("spotify_dl.pipeline.ThreadPoolExecutor", lambda max_workers: executor)
    monkeypatch.setattr("spotify_dl.pipeline.as_completed", lambda futures: iter(futures))

    results = process_tracks(
        config=config,
        source_type="album",
        tracks=[make_track(spotify_id=str(index)) for index in range(4)],
        options={"skip_existing": True, "dry_run": False, "verbose": False},
    )

    assert executor.max_workers == 3
    assert len(executor.submitted) == 4
    assert executor.shutdown_args == {"wait": True}
    assert [result.status for result in results] == ["done", "done", "done", "done"]


def test_track_processing_stays_sequential(tmp_path, monkeypatch):
    config = _app_config(tmp_path, concurrency=3)
    calls = []

    class FakePipeline:
        def __init__(self, *args, **kwargs):
            pass

        def process_track(self, track, **kwargs):
            calls.append(track.spotify_id)
            return DownloadResult(track, None, None, tmp_path / "out.mp3", "done", None)

    monkeypatch.setattr("spotify_dl.pipeline.DownloadPipeline", FakePipeline)
    monkeypatch.setattr(
        "spotify_dl.pipeline.ThreadPoolExecutor",
        lambda max_workers: (_ for _ in ()).throw(AssertionError("track should not use workers")),
    )

    process_tracks(
        config=config,
        source_type="track",
        tracks=[make_track(spotify_id="track-id")],
        options={"skip_existing": True, "dry_run": False, "verbose": False},
    )

    assert calls == ["track-id"]


def _app_config(tmp_path, *, concurrency: int) -> AppConfig:
    return AppConfig(
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
        concurrency=concurrency,
    )
