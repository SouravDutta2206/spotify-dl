from __future__ import annotations

import pytest

from concurrent.futures import Future

from spotify_dl.models import AccountProfile
from spotify_dl.pipeline import process_tracks
from spotify_dl.models import DownloadResult
from tests.conftest import make_track


def _parse_download_args(argv):
    from spotify_dl.cli_utils import build_parser

    parser = build_parser()
    return parser, parser, parser.parse_args(["download", *argv])


def test_cli_alias_calls_main(monkeypatch):
    from spotify_dl import main as main_module

    calls = []
    monkeypatch.setattr(main_module, "main", lambda: calls.append("main"))

    main_module.main()

    assert calls == ["main"]


def test_profile_command_prints_account_fields(monkeypatch, capsys):
    from spotify_dl import main as main_module

    class FakeSpotify:
        def get_current_user_profile(self):
            return AccountProfile(
                display_name="LOL",
                spotify_user_id="h1cvqfami8l5l35hrohkcmt5b",
                account_type="premium",
                account_id="R6621MQqcn",
                country="IN",
                email="user@example.com",
                followers=0,
                explicit_filter_enabled=False,
            )

    monkeypatch.setattr("sys.argv", ["spotify-dl", "profile"])
    monkeypatch.setattr(
        main_module,
        "spotify_client_from_options",
        lambda options: (None, FakeSpotify()),
    )

    main_module.main()

    assert capsys.readouterr().out.splitlines() == [
        "Display name: LOL",
        "Spotify user ID: h1cvqfami8l5l35hrohkcmt5b",
        "Account type: premium",
        "Account ID: R6621MQqcn",
        "Country: IN",
        "Email: user@example.com",
        "Followers: 0",
        "Explicit filter: False",
    ]


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


def test_parse_download_manifest_groups_tracks_and_collections(tmp_path):
    from spotify_dl.manifest import parse_download_manifest

    manifest_path = tmp_path / "links.txt"
    manifest_path.write_text(
        "\n".join(
            [
                "# batch manifest",
                "[tracks]",
                "spotify:track:track123",
                "spotify:track:track456 | https://youtube.com/watch?v=second",
                "",
                "[playlists]",
                "spotify:playlist:playlist123",
                "",
                "[album]",
                "spotify:album:album123",
            ]
        ),
        encoding="utf-8",
    )

    manifest = parse_download_manifest(manifest_path)

    assert [(track.spotify_url, track.youtube_url) for track in manifest.tracks] == [
        ("spotify:track:track123", None),
        ("spotify:track:track456", "https://youtube.com/watch?v=second"),
    ]
    assert manifest.collections == [
        "spotify:playlist:playlist123",
        "spotify:album:album123",
    ]


def test_download_validation_loads_manifest_from_file(tmp_path):
    from spotify_dl.main import validate_download

    manifest_path = tmp_path / "links.txt"
    manifest_path.write_text("[tracks]\nspotify:track:track123\n", encoding="utf-8")
    _, download_parser, args = _parse_download_args(["--from-file", str(manifest_path)])

    validate_download(args, download_parser)

    assert args.download_manifest.tracks[0].spotify_url == "spotify:track:track123"


def test_download_validation_rejects_from_file_with_urls(tmp_path):
    from spotify_dl.main import validate_download

    manifest_path = tmp_path / "links.txt"
    manifest_path.write_text("[tracks]\nspotify:track:track123\n", encoding="utf-8")
    _, download_parser, args = _parse_download_args(
        ["spotify:track:other123", "--from-file", str(manifest_path)]
    )

    with pytest.raises(SystemExit) as exc_info:
        validate_download(args, download_parser)

    assert exc_info.value.code == 2


def test_download_validation_rejects_youtube_link_in_collection_section(tmp_path):
    from spotify_dl.main import validate_download

    manifest_path = tmp_path / "links.txt"
    manifest_path.write_text(
        "[playlists]\nspotify:playlist:playlist123 | https://youtube.com/watch?v=bad\n",
        encoding="utf-8",
    )
    _, download_parser, args = _parse_download_args(["--from-file", str(manifest_path)])

    with pytest.raises(SystemExit) as exc_info:
        validate_download(args, download_parser)

    assert exc_info.value.code == 2


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
            return False

    class FakeExecutor:
        def __init__(self, max_workers, *args, **kwargs):
            self.max_workers = max_workers
            self.shutdown_args = None

        def submit(self, *args, **kwargs):
            return FakeFuture()

        def shutdown(self, **kwargs):
            self.shutdown_args = kwargs

    def fake_sleep(seconds):
        raise KeyboardInterrupt

    executor = FakeExecutor(max_workers=5)
    monkeypatch.setattr("spotify_dl.pipeline.ThreadPoolExecutor", lambda max_workers, **kwargs: executor)
    monkeypatch.setattr("spotify_dl.pipeline.time.sleep", fake_sleep)
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

    class FakeExecutor:
        def __init__(self, max_workers, *args, **kwargs):
            self.max_workers = max_workers
            self.submitted = []
            self.shutdown_args = None

        def submit(self, func, track, **kwargs):
            self.submitted.append((func, track, kwargs))
            future = Future()
            future.set_result(DownloadResult(track, None, tmp_path / "out.mp3", "done", None))
            return future

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


def test_download_validation_allows_tracks_with_youtube_link_skip_placeholders():
    from spotify_dl.main import validate_download

    _, download_parser, args = _parse_download_args(
        [
            "https://open.spotify.com/track/track123",
            "spotify:track:track456",
            "--youtube-link",
            "_",
            "https://youtube.com/watch?v=second",
        ]
    )

    validate_download(args, download_parser)


def test_dispatch_download_with_youtube_link_skip(monkeypatch):
    from spotify_dl.main import _dispatch_download

    _, _, args = _parse_download_args(
        [
            "https://open.spotify.com/track/track123",
            "spotify:track:track456",
            "--youtube-link",
            "_",
            "https://youtube.com/watch?v=second",
        ]
    )

    downloaded = []
    def fake_run_download(urls, options):
        downloaded.append((urls, options))

    monkeypatch.setattr("spotify_dl.main.run_download", fake_run_download)

    _dispatch_download(args)

    assert len(downloaded) == 2
    assert downloaded[0][0] == "https://open.spotify.com/track/track123"
    assert downloaded[0][1]["youtube_link"] is None
    assert downloaded[0][1]["youtube_link_map"] == {
        "track123": None,
        "track456": "https://youtube.com/watch?v=second",
    }
    
    assert downloaded[1][0] == "spotify:track:track456"
    assert downloaded[1][1]["youtube_link"] == "https://youtube.com/watch?v=second"


def test_dispatch_download_from_manifest_separates_tracks_and_collections(tmp_path, monkeypatch):
    from spotify_dl.main import _dispatch_download, validate_download

    manifest_path = tmp_path / "links.txt"
    manifest_path.write_text(
        "\n".join(
            [
                "[tracks]",
                "spotify:track:track123",
                "spotify:track:track456 | https://youtube.com/watch?v=second",
                "[playlists]",
                "spotify:playlist:playlist123",
                "[albums]",
                "spotify:album:album123",
            ]
        ),
        encoding="utf-8",
    )
    _, download_parser, args = _parse_download_args(["--from-file", str(manifest_path)])
    validate_download(args, download_parser)

    downloaded = []

    def fake_run_download(urls, options):
        downloaded.append((urls, options))

    monkeypatch.setattr("spotify_dl.main.run_download", fake_run_download)

    _dispatch_download(args)

    assert [call[0] for call in downloaded] == [
        "spotify:track:track123",
        "spotify:track:track456",
        "spotify:playlist:playlist123",
        "spotify:album:album123",
    ]
    assert downloaded[0][1]["youtube_link"] is None
    assert downloaded[0][1]["youtube_link_map"] == {
        "track456": "https://youtube.com/watch?v=second",
    }
    assert downloaded[1][1]["youtube_link"] is None
    assert downloaded[1][1]["youtube_link_map"] == {
        "track456": "https://youtube.com/watch?v=second",
    }
    assert downloaded[2][1]["youtube_link_map"] == {
        "track456": "https://youtube.com/watch?v=second",
    }
