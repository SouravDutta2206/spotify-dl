from __future__ import annotations

import click

from spotify_dl.commands.common import (
    merge_cli_options,
    normalize_download_options,
    options_to_config_partial,
)


def test_merge_cli_options_merges_ancestors():
    @click.group()
    @click.option("--output", "-o", "output_directory", default=None)
    def root():
        pass

    @root.command()
    @click.option("--verbose", "-v", is_flag=True, default=None)
    def child(verbose):
        pass

    ctx = click.Context(child)
    ctx.parent = click.Context(root)
    ctx.parent.params = {"output_directory": "/music"}
    ctx.params = {"verbose": True}

    assert merge_cli_options(ctx, verbose=True) == {
        "output_directory": "/music",
        "verbose": True,
    }


def test_normalize_download_options_defaults():
    assert normalize_download_options({}) == {
        "skip_existing": True,
        "dry_run": False,
        "verbose": False,
        "youtube_link": None,
        "make_playlist": False,
    }


def test_normalize_download_options_force_skip_existing():
    options = normalize_download_options({"skip_existing": False}, force_skip_existing=True)
    assert options["skip_existing"] is True


def test_options_to_config_partial_maps_cli_keys():
    partial = options_to_config_partial(
        {
            "client_id": "id",
            "output_directory": "~/Music",
            "quality": "320",
            "auth_callback_port": 9999,
            "concurrency": 4,
        }
    )
    assert partial == {
        "spotify": {"client_id": "id"},
        "output": {"directory": "~/Music", "quality": "320"},
        "auth": {"callback_port": 9999},
        "concurrency": 4,
    }
