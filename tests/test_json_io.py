from __future__ import annotations

from spotify_dl.json_io import read_json, write_json_atomic


def test_write_json_atomic_creates_parent_and_round_trips(tmp_path):
    path = tmp_path / "nested" / "data.json"

    write_json_atomic(path, {"name": "spotify-dl", "count": 2})

    assert read_json(path) == {"name": "spotify-dl", "count": 2}
    assert not path.with_suffix(".json.tmp").exists()
