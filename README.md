# spotify-dl

`spotify-dl` takes Spotify track, album, or playlist URLs, resolves metadata from Spotify,
matches audio on YouTube, downloads MP3s with `yt-dlp`, and writes complete ID3 tags.

This repository is an implementation-in-progress following `spotify-dl-spec.md`.

## Quick start

```bash
pip install -e ".[dev]"
spotify-dl config set client-id YOUR_ID
spotify-dl config set client-secret YOUR_SECRET
spotify-dl https://open.spotify.com/track/...
```

You also need `ffmpeg` on your `PATH` for real downloads.

## Link manifests

Batch downloads can be loaded from a plain text manifest:

```bash
spotify-dl download --from-file links.txt
```

```txt
[tracks]
spotify:track:abc123
spotify:track:def456 | https://www.youtube.com/watch?v=xyz789

[playlists]
spotify:playlist:foo

[albums]
spotify:album:bar
```

Track entries may include a YouTube link after `|` to skip YouTube search for that
track. Album and playlist entries are downloaded separately without YouTube overrides.
