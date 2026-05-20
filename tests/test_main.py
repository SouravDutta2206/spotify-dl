from __future__ import annotations

import pytest

from spotify_dl.pipeline import process_tracks
from spotify_dl.models import AppConfig, DownloadResult
from tests.conftest import make_track


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

        def done(self):
            # Raise KeyboardInterrupt when checking done status to simulate a keyboard interrupt
            raise KeyboardInterrupt

        def result(self):
            raise AssertionError("result should not be called")

    class FakeExecutor:
        def __init__(self, max_workers, *args, **kwargs):
            self.max_workers = max_workers
            self.shutdown_args = None

        def submit(self, *args, **kwargs):
            return FakeFuture()

        def shutdown(self, **kwargs):
            self.shutdown_args = kwargs

    executor = FakeExecutor(max_workers=5)
    monkeypatch.setattr("spotify_dl.pipeline.ThreadPoolExecutor", lambda max_workers, **kwargs: executor)
    monkeypatch.setattr("os._exit", lambda code: (_ for _ in ()).throw(SystemExit(code)))

    with pytest.raises(SystemExit) as exc_info:
        process_tracks(
            config=config,
            source_type="playlist",
            tracks=[make_track(spotify_id=str(index)) for index in range(2)],
            options={"skip_existing": True, "dry_run": False, "verbose": False},
        )

    assert exc_info.value.code == 130
    assert executor.shutdown_args == {"wait": False, "cancel_futures": True}


def test_album_processing_uses_concurrent_workers(app_config, tmp_path, monkeypatch):
    config = app_config

    class FakeFuture:
        def __init__(self, result):
            self._result = result

        def done(self):
            return True

        def result(self):
            return self._result

    class FakeExecutor:
        def __init__(self, max_workers, *args, **kwargs):
            self.max_workers = max_workers
            self.submitted = []
            self.shutdown_args = None

        def submit(self, func, track, **kwargs):
            self.submitted.append((func, track, kwargs))
            return FakeFuture(DownloadResult(track, None, tmp_path / "out.mp3", "done", None))

        def shutdown(self, **kwargs):
            self.shutdown_args = kwargs

    executor = FakeExecutor(max_workers=3)
    monkeypatch.setattr("spotify_dl.pipeline.ThreadPoolExecutor", lambda max_workers, **kwargs: executor)

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


def test_track_processing_stays_sequential(app_config, tmp_path, monkeypatch):
    config = app_config
    calls = []

    class FakePipeline:
        def __init__(self, *args, **kwargs):
            pass

        def process_track(self, track, **kwargs):
            calls.append(track.spotify_id)
            return DownloadResult(track, None, tmp_path / "out.mp3", "done", None)

    monkeypatch.setattr("spotify_dl.pipeline.DownloadPipeline", FakePipeline)
    monkeypatch.setattr(
        "spotify_dl.pipeline.ThreadPoolExecutor",
        lambda max_workers, **kwargs: (_ for _ in ()).throw(AssertionError("track should not use workers")),
    )

    process_tracks(
        config=config,
        source_type="track",
        tracks=[make_track(spotify_id="track-id")],
        options={"skip_existing": True, "dry_run": False, "verbose": False},
    )

    assert calls == ["track-id"]



def test_run_download_normalizes_options(app_config, tmp_path, monkeypatch):
    from spotify_dl.pipeline import run_download
    from unittest.mock import MagicMock

    config = app_config
    client = MagicMock()
    client.resolve_url.return_value = ("track", "Title", [make_track(spotify_id="track-id")])
    
    monkeypatch.setattr(
        "spotify_dl.pipeline.spotify_client_from_options",
        lambda options: (config, client),
    )

    download_calls = []
    monkeypatch.setattr(
        "spotify_dl.pipeline.download_tracks",
        lambda **kwargs: download_calls.append(kwargs),
    )

    # Pass incomplete options, just like CLI does
    run_download("spotify:track:abc", {"output": str(tmp_path)})

    assert len(download_calls) == 1
    opts = download_calls[0]["options"]
    assert opts["verbose"] is False
    assert opts["dry_run"] is False
    assert opts["skip_existing"] is True

