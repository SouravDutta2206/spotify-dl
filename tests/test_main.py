from __future__ import annotations

import pytest

from spotify_dl.pipeline import process_tracks
from spotify_dl.models import DownloadResult
from tests.conftest import make_track


def _parse_download_args(argv):
    from spotify_dl.main import _get_subparser, build_parser

    parser = build_parser()
    return parser, _get_subparser(parser, "download"), parser.parse_args(["download", *argv])


def test_cli_alias_calls_main(monkeypatch):
    from spotify_dl import main as main_module

    calls = []
    monkeypatch.setattr(main_module, "main", lambda: calls.append("main"))

    main_module.main()

    assert calls == ["main"]


def test_download_validation_allows_mixed_sources_without_youtube_link():
    from spotify_dl.main import validate_download

    parser, download_parser, args = _parse_download_args(
        [
            "https://open.spotify.com/track/track123",
            "https://open.spotify.com/album/album123",
        ]
    )

    validate_download(args, download_parser)
    assert parser.prog == "spotify-dl"


def test_download_validation_allows_tracks_with_youtube_link():
    from spotify_dl.main import validate_download

    _, download_parser, args = _parse_download_args(
        [
            "https://open.spotify.com/track/track123",
            "spotify:track:track456",
            "--youtube-link",
            "https://youtube.com/watch?v=first",
            "https://youtube.com/watch?v=second",
        ]
    )

    validate_download(args, download_parser)


@pytest.mark.parametrize(
    "spotify_url",
    [
        "https://open.spotify.com/album/album123",
        "https://open.spotify.com/playlist/playlist123",
    ],
)
def test_download_validation_rejects_collections_when_using_youtube_link(spotify_url):
    from spotify_dl.main import validate_download

    _, download_parser, args = _parse_download_args(
        [
            spotify_url,
            "--youtube-link",
            "https://youtube.com/watch?v=collection",
        ]
    )

    with pytest.raises(SystemExit) as exc_info:
        validate_download(args, download_parser)

    assert exc_info.value.code == 2


def test_concurrent_playlist_processing_aborts_on_keyboard_interrupt(app_config, monkeypatch):
    config = app_config

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

    # Pass incomplete options, and options with None value (like parsed CLI args)
    run_download("spotify:track:abc", {
        "output": str(tmp_path),
        "skip_existing": None,
        "dry_run": None,
        "verbose": None,
        "make_playlist": None,
    })

    assert len(download_calls) == 1
    opts = download_calls[0]["options"]
    assert opts["verbose"] is False
    assert opts["dry_run"] is False
    assert opts["skip_existing"] is True
    assert opts["make_playlist"] is False

