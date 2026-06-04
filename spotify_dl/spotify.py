from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from spotify_dl.auth import USER_SCOPES, build_spotify_oauth
from spotify_dl.config import ConfigManager
from spotify_dl.exceptions import SpotifyError
from spotify_dl.models import AccountProfile, AppConfig, PlaylistSummary, TrackMetadata
from spotify_dl.source_cache import CoverCache, SourceCache


SPOTIFY_URL_RE = re.compile(
    r"https?://open\.spotify\.com/(?P<kind>track|album|playlist)/(?P<id>[A-Za-z0-9]+)"
)
SPOTIFY_URI_RE = re.compile(
    r"spotify:(?P<kind>track|album|playlist):(?P<id>[A-Za-z0-9]+)"
)

BATCH_TRACK_THRESHOLD = 5

def parse_spotify_url(
    url: str,
) -> tuple[Literal["track", "album", "playlist"] | None, str | None]:
    match = SPOTIFY_URL_RE.search(url) or SPOTIFY_URI_RE.fullmatch(url)
    if not match:
        return None, None
    return match.group("kind"), match.group("id")

def _best_image(images: list[dict[str, Any]]) -> str:
    if not images:
        return ""
    return max(images, key=lambda image: image.get("height") or 0).get("url", "")

def _album_total_discs(album: dict[str, Any], tracks: list[dict[str, Any]] | None = None) -> int:
    candidates = tracks or album.get("tracks", {}).get("items", [])
    return max([item.get("disc_number", 1) for item in candidates] or [1])

def _playlist_track_count(item: dict[str, Any]) -> int:
    tracks = item.get("tracks") or {}
    if isinstance(tracks, dict):
        return int(tracks.get("total") or 0)
    return 0

def _iter_page_items(client, page: dict[str, Any]):
    while True:
        yield from page.get("items", [])
        if not page.get("next"):
            break
        page = client.next(page)

def track_from_spotify(track: dict[str, Any], album_override: dict[str, Any] | None = None) -> TrackMetadata:
    album = album_override or track["album"]
    album_tracks = album.get("tracks", {}).get("items", [])
    return TrackMetadata(
        spotify_id=track["id"],
        isrc=(track.get("external_ids") or {}).get("isrc"),
        title=track["name"],
        artists=[artist["name"] for artist in track.get("artists", [])],
        track_number=int(track.get("track_number") or 1),
        disc_number=int(track.get("disc_number") or 1),
        duration_ms=int(track.get("duration_ms") or 0),
        album_id=album["id"],
        album_name=album["name"],
        album_artist=(album.get("artists") or [{"name": "Unknown Artist"}])[0]["name"],
        album_total_tracks=int(album.get("total_tracks") or len(album_tracks) or 1),
        album_total_discs=_album_total_discs(album, album_tracks),
        album_release_date=album.get("release_date") or "",
        album_art_url=_best_image(album.get("images", [])),
        album_genres=album.get("genres") or [],
    )

class SpotifyClient:
    def __init__(
        self,
        config: AppConfig,
        config_manager: ConfigManager | None = None,
        cache_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.config_manager = config_manager
        self._public_sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=config.spotify_client_id,
                client_secret=config.spotify_client_secret,
            ),
            requests_timeout=20,
            retries=3,
        )
        self._user_sp: spotipy.Spotify | None = None
        _cache_dir = (cache_dir or Path.home() / ".spotify-dl" / "cache").expanduser()
        self.source_cache = SourceCache(_cache_dir)
        self.cover_cache = CoverCache(_cache_dir)

    def resolve_url(
        self,
        url: str,
    ) -> tuple[str, str, list[TrackMetadata]]:
        kind, item_id = parse_spotify_url(url)
        if kind == "track":
            track = self.get_track(item_id)
            return kind, track.title, [track]
        if kind == "album":
            tracks = self.get_album(item_id)
            name = tracks[0].album_name if tracks else "Album"
            return kind, name, tracks
        header = self.get_playlist_header(item_id)
        tracks = self.get_playlist(
            item_id,
            snapshot_id=header.get("snapshot_id"),
            playlist_name=header.get("name"),
        )
        return kind, header["name"], tracks

    def get_track(self, track_id: str) -> TrackMetadata:
        cached = self.source_cache.read_track(track_id)
        if cached:
            track, _ = cached
            return track
        try:
            track = track_from_spotify(self._api().track(track_id))
            self.source_cache.write_track(track)
            return track
        except Exception as exc:
            raise SpotifyError(f"Track not found on Spotify: {track_id}") from exc

    def get_album(self, album_id: str) -> list[TrackMetadata]:
        payload = self.source_cache.read_collection("album", album_id)
        if payload:
            return [TrackMetadata(**track) for track in payload.get("tracks", [])]
        try:
            api = self._api()
            album = api.album(album_id)
            track_items = list(_iter_page_items(api, album["tracks"]))
            track_ids = [item["id"] for item in track_items if item.get("id")]
            with ThreadPoolExecutor(max_workers=min(10, len(track_ids) or 1)) as pool:
                full_tracks = list(pool.map(api.track, track_ids))
            metadata = [
                track_from_spotify(track, album)
                for track in full_tracks
                if track
            ]
            self.source_cache.write_collection(
                "album",
                album_id,
                album.get("name") or album_id,
                metadata,
            )
            return metadata
        except Exception as exc:
            raise SpotifyError(f"Album not found on Spotify: {album_id}") from exc

    def get_playlist_header(self, playlist_id: str) -> dict[str, Any]:
        return self._api().playlist(playlist_id, fields="id,name,snapshot_id,tracks(total),external_urls")

    def get_playlist(
        self,
        playlist_id: str,
        *,
        snapshot_id: str | None = None,
        playlist_name: str | None = None,
    ) -> list[TrackMetadata]:
        try:
            api = self._api()
            if snapshot_id is None or playlist_name is None:
                header = self.get_playlist_header(playlist_id)
                snapshot_id = header.get("snapshot_id")
                playlist_name = header.get("name")
            payload = self.source_cache.read_collection("playlist", playlist_id)
            if payload and (snapshot_id is None or payload.get("snapshot_id") == snapshot_id):
                return [TrackMetadata(**track) for track in payload.get("tracks", [])]
            page = api.playlist_items(playlist_id, limit=100, offset=0)
            tracks: list[TrackMetadata] = []
            for item in _iter_page_items(api, page):
                track = (item.get("track") or item.get("item")) if item else None
                if (
                    not track
                    or track.get("type") != "track"
                    or not track.get("id")
                    or track.get("is_local")
                ):
                    continue
                tracks.append(track_from_spotify(track))
            if snapshot_id != 'temp':
                self.source_cache.write_collection(
                    "playlist",
                    playlist_id,
                    playlist_name or playlist_id,
                    tracks,
                    snapshot_id=snapshot_id,
                )
            return tracks
        except SpotifyError:
            raise
        except Exception as exc:
            raise SpotifyError(f"Playlist not found on Spotify: {playlist_id}") from exc

    def list_user_playlists(self) -> list[PlaylistSummary]:
        api = self._api(require_user=True)
        playlists: list[PlaylistSummary] = []
        page = api.current_user_playlists(limit=50)
        for item in _iter_page_items(api, page):
            visibility = (
                "collaborative"
                if item.get("collaborative")
                else ("public" if item.get("public") else "private")
            )
            track_count = _playlist_track_count(item)
            if track_count == 0:
                track_count = self.get_playlist_track_count(item["id"])
            playlists.append(
                PlaylistSummary(
                    playlist_id=item["id"],
                    name=item["name"],
                    owner=(item.get("owner") or {}).get("display_name") or "Unknown",
                    track_count=track_count,
                    visibility=visibility,  # type: ignore[arg-type]
                    cover_art_url=_best_image(item.get("images", [])) or None,
                    spotify_url=(item.get("external_urls") or {}).get("spotify", ""),
                )
            )
        return playlists

    def get_current_user_profile(self) -> AccountProfile:
        api = self._api(require_user=True)
        try:
            user = api.current_user()
            explicit_content = user.get("explicit_content") or {}
            followers = user.get("followers") or {}
            return AccountProfile(
                display_name=user.get("display_name") or "",
                spotify_user_id=user.get("id") or "",
                account_type=user.get("product") or "",
                account_id=user.get("account_id") or "",
                country=user.get("country") or "",
                email=user.get("email") or "",
                followers=int(followers.get("total") or 0),
                explicit_filter_enabled=bool(explicit_content.get("filter_enabled")),
            )
        except Exception as exc:
            raise SpotifyError("Could not fetch Spotify account profile") from exc

    def get_playlist_track_count(self, playlist_id: str) -> int:
        api = self._api(require_user=True)
        try:
            page = api.playlist_items(playlist_id, limit=1, offset=0, fields="total")
            return int(page.get("total") or 0)
        except Exception:
            pass
        try:
            header = api.playlist(playlist_id, fields="tracks(total)")
            return int(((header.get("tracks") or {}).get("total")) or 0)
        except Exception:
            return 0

    def _api(self, *, require_user: bool = False) -> spotipy.Spotify:
        """Return the best available client. User-auth preferred when available."""
        if self.config.spotify_user_access_token or self.config.spotify_user_refresh_token:
            expiry = self.config.spotify_user_token_expiry
            token_expires_soon = (
                expiry is None
                or expiry <= datetime.now(timezone.utc) + timedelta(minutes=5)
            )
            if token_expires_soon:
                self._refresh_user_token()
                self._user_sp = None
            if self._user_sp is None:
                if not self.config.spotify_user_access_token:
                    raise SpotifyError("Run spotify-dl auth login first")
                self._user_sp = spotipy.Spotify(auth=self.config.spotify_user_access_token)
            return self._user_sp
        if require_user:
            raise SpotifyError("Run spotify-dl auth login first")
        return self._public_sp

    def _refresh_user_token(self) -> None:
        if not self.config.spotify_user_refresh_token:
            raise SpotifyError("Run spotify-dl auth login first")
        if not self.config_manager:
            raise SpotifyError("User token expired. Run spotify-dl auth login again.")
        oauth = build_spotify_oauth(self.config, open_browser=False)
        token_info = oauth.refresh_access_token(self.config.spotify_user_refresh_token)
        expiry = datetime.fromtimestamp(token_info["expires_at"], tz=timezone.utc)
        refresh_token = token_info.get("refresh_token") or self.config.spotify_user_refresh_token
        self.config_manager.save_user_auth(
            access_token=token_info["access_token"],
            refresh_token=refresh_token,
            token_expiry=expiry,
            scope=token_info.get("scope") or USER_SCOPES,
        )
        self.config.spotify_user_access_token = token_info["access_token"]
        self.config.spotify_user_refresh_token = refresh_token
        self.config.spotify_user_token_expiry = expiry

    def batch_resolve_tracks(self, track_ids: list[str]) -> list[TrackMetadata]:
        """Resolve many track IDs efficiently via a temporary playlist."""
        # 1. Check source cache
        cached: dict[str, TrackMetadata] = {}
        uncached_ids: list[str] = []
        for tid in track_ids:
            result = self.source_cache.read_track(tid)
            if result:
                cached[tid] = result[0]
            else:
                uncached_ids.append(tid)

        if not uncached_ids:
            return [cached[tid] for tid in track_ids]

        # 2. Below threshold → per-track fallback
        if len(uncached_ids) <= BATCH_TRACK_THRESHOLD:
            for tid in uncached_ids:
                cached[tid] = self.get_track(tid)
            return [cached[tid] for tid in track_ids]

        # 3. Create temp playlist, fetch metadata via get_playlist(), then delete
        api = self._api(require_user=True)
        playlist = api._post("me/playlists", payload={
            "name": "_spotify-dl-temp",
            "public": False,
            "description": "Temporary playlist for spotify-dl batch resolution.",
        })
        playlist_id = playlist["id"]
        try:
            uris = [f"spotify:track:{tid}" for tid in uncached_ids]
            for i in range(0, len(uris), 100):
                api.playlist_add_items(playlist_id, uris[i:i + 100])

            tracks = self.get_playlist(
                playlist_id, snapshot_id="temp", playlist_name="_spotify-dl-temp",
            )
        finally:
            api._delete(f"/playlists/{playlist_id}/followers")

        for track in tracks:
            self.source_cache.write_track(track)
            cached[track.spotify_id] = track

        return [cached[tid] for tid in track_ids if tid in cached]
