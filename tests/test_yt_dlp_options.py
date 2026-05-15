from __future__ import annotations

from spotify_dl.yt_dlp_options import javascript_runtime_options


def test_javascript_runtime_prefers_deno(monkeypatch):
    monkeypatch.setattr(
        "spotify_dl.yt_dlp_options.shutil.which",
        lambda name: {"deno": "C:/deno.exe", "node": "C:/node.exe"}.get(name),
    )

    assert javascript_runtime_options() == {"deno": {"path": "C:/deno.exe"}}


def test_javascript_runtime_falls_back_to_node(monkeypatch):
    monkeypatch.setattr(
        "spotify_dl.yt_dlp_options.shutil.which",
        lambda name: {"node": "C:/node.exe"}.get(name),
    )

    assert javascript_runtime_options() == {"node": {"path": "C:/node.exe"}}

