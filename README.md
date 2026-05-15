# spotify-dl

`spotify-dl` takes Spotify track, album, or playlist URLs, resolves metadata from Spotify,
matches audio on YouTube, downloads MP3s with `yt-dlp`, and writes complete ID3 tags.

This repository is an implementation-in-progress following `spotify-dl-spec.md`.

## Quick start

```bash
pip install -e ".[dev]"
spotify-dl config set --client-id YOUR_ID --client-secret YOUR_SECRET
spotify-dl https://open.spotify.com/track/...
```

You also need `ffmpeg` on your `PATH` for real downloads.

