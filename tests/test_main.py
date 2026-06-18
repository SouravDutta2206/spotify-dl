from __future__ import annotations

import pytest

from spotify_dl.models import AccountProfile


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
    assert downloaded[0][1].youtube_link is None
    assert downloaded[0][1].youtube_link_map == {
        "track123": None,
        "track456": "https://youtube.com/watch?v=second",
    }
    
    assert downloaded[1][0] == "spotify:track:track456"
    assert downloaded[1][1].youtube_link == "https://youtube.com/watch?v=second"


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
    assert downloaded[0][1].youtube_link is None
    assert downloaded[0][1].youtube_link_map == {
        "track456": "https://youtube.com/watch?v=second",
    }
    assert downloaded[1][1].youtube_link is None
    assert downloaded[1][1].youtube_link_map == {
        "track456": "https://youtube.com/watch?v=second",
    }
    assert downloaded[2][1].youtube_link_map == {
        "track456": "https://youtube.com/watch?v=second",
    }
