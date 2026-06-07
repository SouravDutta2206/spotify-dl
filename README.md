# spotify-dl 🎵

`spotify-dl` resolves track metadata, albums, or playlist URLs from Spotify, matches the audio on YouTube, downloads high-quality MP3s via `yt-dlp`, and embeds complete ID3 tags (artist, album, track name, cover art, track number, etc.) into the files.

---

## Prerequisites

Before installing and configuring `spotify-dl`, ensure the following dependencies are installed and available on your system's `PATH`:

1. **Python 3.11+**
2. **ffmpeg**: Required for audio transcoding and writing metadata.
3. **Node.js 20**: Required by the `yt-dlp-ejs` engine for YouTube download processing.
4. **Spotify Premium Account**: Required to register an app on the Spotify Developer Dashboard and authenticate your library.

---

## Installation

### 💻 Windows Installation

#### Option 1: Automated Script (PowerShell)

You can automatically download and install all dependencies (Python 3.11, Node.js 20, FFmpeg, pipx) and `spotify-dl` by running this command in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -Command "Invoke-Expression (Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/SouravDutta2206/spotify-dl/main/install.ps1' -UseBasicParsing).Content"
```

#### Option 2: Manual Installation

Ensure you have a global Python installation and that it is added to your Environment Variables (`PATH`).

##### Using `uv` (Recommended)

`uv` is an extremely fast Python package and tool installer.

- **As a standalone tool (recommended):**

  ```powershell
  uv tool install --git https://github.com/SouravDutta2206/spotify-dl.git
  ```

- **Inside a global environment via `uv pip`:**
  ```powershell
  uv pip install git+https://github.com/SouravDutta2206/spotify-dl.git
  ```

##### Using standard `pip`

Install globally to your Python environment:

```powershell
pip install git+https://github.com/SouravDutta2206/spotify-dl.git
```

> [!TIP]
> Ensure you download and install [ffmpeg](https://ffmpeg.org/download.html) and [Node.js 20](https://nodejs.org/en) on Windows, ensuring both binaries are added to your System Path.

---

### 🐧 Linux Installation

#### Option 1: Automated script (Debian/Ubuntu-based distros)

Use our installation script which automatically installs Python 3.11 (if needed), Node.js 20, `pipx`, `ffmpeg`, and `spotify-dl`:

```bash
curl -fsSL https://raw.githubusercontent.com/SouravDutta2206/spotify-dl/main/install.sh | bash
```

#### Option 2: Manual installation

1. Update package lists and install basic Python and media tools:

   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv python3-dev ffmpeg curl gnupg ca-certificates
   ```

2. Install **Node.js 20** from the NodeSource repository:

   ```bash
   curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
   sudo apt install -y nodejs
   ```

3. Install `pipx` to manage global Python packages and ensure it is added to your shell path:

   ```bash
   sudo apt install -y pipx
   pipx ensurepath
   # Reload shell settings
   source ~/.bashrc
   ```

4. Install `spotify-dl` via `pipx`:
   ```bash
   pipx install git+https://github.com/SouravDutta2206/spotify-dl.git
   ```

---

## Spotify Developer Setup

To use this application, you must authenticate with the Spotify API by registering a developer application:

1. Log into the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) (requires a **Spotify Premium Account**).
2. Click **Create app**.
3. Fill out the application details.
4. **CRITICAL**: Set the **Redirect URI** to exactly:
   `http://127.0.0.1:8888/callback`
   > [!IMPORTANT]
   > Do **NOT** use `localhost:8888/callback`. Spotify OAuth strict matching requires `127.0.0.1:8888`.
5. Save the app and retrieve the **Client ID** and **Client Secret** from the App settings page.

Save these credentials to your `spotify-dl` configuration:

```bash
spotify-dl config set client-id YOUR_CLIENT_ID
spotify-dl config set client-secret YOUR_CLIENT_SECRET
```

---

## Authentication Modes

### 🌐 Head Mode (Default)

If you are running the app on a machine with a web browser (Windows, macOS, or Linux Desktop), run:

```bash
spotify-dl auth login
```

This will automatically open your default browser. Grant permissions to the application, and you will be redirected to a success page.

---

### 🖥️ Headless Mode (CLI/Servers)

If you are running `spotify-dl` on a headless server, remote VM, or terminal environment without a display, set `SPOTIFY_DL_HEADLESS=1` before running login:

```bash
export SPOTIFY_DL_HEADLESS=1
spotify-dl auth login
```

**Headless Flow:**

1. The terminal will print an authorization URL.
2. Copy this URL and open it in a web browser on any device.
3. Authenticate with your Spotify account.
4. Once completed, your browser will redirect to a page that fails to load (e.g., `http://127.0.0.1:8888/callback?code=...`).
5. Copy the **entire redirect URL** from the browser address bar, paste it back into your terminal prompt, and press Enter to finish authentication.

To verify your login status at any time, run:

```bash
spotify-dl auth status
```

To clear credentials and logout:

```bash
spotify-dl auth logout
```

---

## Configuration Reference

You can display or edit your persistent settings using `spotify-dl config`.

```bash
# View current config
spotify-dl config show

# Set a setting
spotify-dl config set <key> <value>

# Reset configuration to defaults
spotify-dl config clear
```

### Config Keys

| Config Key             | Description                                                 | Default Value        | Valid Options / Details                                                                 |
| :--------------------- | :---------------------------------------------------------- | :------------------- | :-------------------------------------------------------------------------------------- |
| `client-id`            | Spotify API client ID                                       | `null`               | String                                                                                  |
| `client-secret`        | Spotify API client secret                                   | `null`               | String                                                                                  |
| `output`               | Download directory for MP3 files                            | `~/Music/spotify-dl` | Path string                                                                             |
| `quality`              | Audio quality bit rate (kbps)                               | `0` (Best)           | `0`, `128`, `192`, `320`                                                                |
| `concurrency`          | Number of parallel download threads                         | `5`                  | Integer                                                                                 |
| `auth-port`            | Port for the local OAuth redirect server                    | `8888`               | Integer                                                                                 |
| `youtube-cookies-from` | Browser to extract cookies from (for age-restricted videos) | `null`               | `brave`, `chrome`, `chromium`, `edge`, `firefox`, `opera`, `safari`, `vivaldi`, `whale` |
| `youtube-cookie-file`  | Path to a Netscape format cookie file                       | `null`               | Path to `cookies.txt`                                                                   |

---

## Commands

### `download`

Download Spotify tracks, albums, or playlists.

```bash
# Download a track
spotify-dl download "https://open.spotify.com/track/4PTG3Z6ehGkBF3zI7Y8G2y"

# Download a playlist or album
spotify-dl download "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGsyNa7T"

# Run a download dry run (simulated download)
spotify-dl download "<url>" --dry-run

# Override output destination and quality for a run
spotify-dl download "<url>" -o ~/Desktop/MyMusic -q 320
```

#### Skip YouTube search with exact overrides

Provide custom YouTube URLs matching your Spotify track positions (use `_` to search normally for a position):

```bash
spotify-dl download "spotify_url_1" "spotify_url_2" --youtube-link "youtube_url_1" _
```

#### Download via Link Manifests

Save URLs in an INI-style `links.txt` manifest:

```bash
spotify-dl download --from-file links.txt
```

**`links.txt` Example:**

```ini
[tracks]
https://open.spotify.com/track/SomeRandonSong
https://open.spotify.com/track/SomeOtherRandomSong | https://www.youtube.com/watch?v=xyz789

[playlists]
https://open.spotify.com/playlist/myGymPlaylist

[albums]
https://open.spotify.com/album/myFavoriteAlbum
```

---

### `playlists`

Manage and sync your account's saved playlists.

```bash
# List all playlists on your profile
spotify-dl playlists list

# Sync all saved playlists to your output directory
spotify-dl playlists sync --concurrency 8
```

---

### `profile`

Displays basic profile information of the authenticated user.

```bash
spotify-dl profile
```

---

## Command-Line Flags Reference

The `download` and `playlists sync` commands accept several flags that override your persistent configuration or specify custom options for a single run:

### Output Options

- **`-o, --output DIR`**: Directory where the downloaded MP3 files are saved. Overrides the persistent `output` config.
- **`-q, --quality QUALITY`**: Specify audio quality bit rate. Choices: `0` (Best/Lossless), `128`, `192`, `320`. Overrides the persistent `quality` config.
- **`--make-playlist`**: If enabled, mirrors the playlist/album structure by saving tracks into a sub-folder matching the playlist/album name.
- **`--skip-existing` / `--no-skip-existing`**: Toggle whether to skip tracks that already exist locally. (Default: `--skip-existing` is enabled).
- **`-c, --concurrency N`**: The number of concurrent download threads/workers. Overrides persistent `concurrency` config.
- **`--dry-run`**: Run a simulation of the download process. Fetches Spotify metadata and matches YouTube videos, but does not download files.

### Auth / API Options

- **`--client-id ID`**: Overrides the stored Spotify API Client ID for this run.
- **`--client-secret SECRET`**: Overrides the stored Spotify API Client Secret for this run.
- **`--auth-port PORT`**: Specify a custom port for the local OAuth redirect server.

### YouTube / Cookies Options

- **`--youtube-cookies-from BROWSER`**: Automatically extracts YouTube cookies from the specified browser (useful for age-restricted or geo-blocked tracks). Choices: `brave`, `chrome`, `chromium`, `edge`, `firefox`, `opera`, `safari`, `vivaldi`, `whale`.
- **`--youtube-cookie-file FILE`**: Path to an exported Netscape-format cookies.txt file for YouTube.

---

### Command-Specific Flags

#### For the `download` command:

- **`--from-file PATH`**: Loads Spotify URLs and optional YouTube link overrides from a manifest file.
- **`--youtube-link URL [URL ...]`**: Specifies exact YouTube video overrides matching your positional Spotify track URLs (use `_` to run normal YouTube search for that index).

---

## Troubleshooting

### Permission Denied (Linux/macOS)

If you encounter permission errors when downloading music or writing config/cache files (such as `PermissionError: [Errno 13] Permission denied`), ensure your user owns the output music directory and the configuration/cache directory. You can fix the ownership by running:

```bash
sudo chown -R $USER:$USER ~/Music/spotify-dl ~/.spotify-dl #add your own custom paths if needed
```
