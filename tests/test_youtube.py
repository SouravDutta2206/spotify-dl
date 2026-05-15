from __future__ import annotations

from spotify_dl.youtube import YouTubeSearcher
from tests.test_filesystem import make_track


def test_youtube_duration_and_text_score():
    track = make_track(title="Song", artists=["Artist"], duration_ms=180000)
    match = YouTubeSearcher()._score(
        {"id": "vid", "title": "Artist - Song audio", "duration": 181},
        track,
        "Artist - Song audio",
    )

    assert match.match_score >= 90
    assert match.youtube_url == "https://www.youtube.com/watch?v=vid"

