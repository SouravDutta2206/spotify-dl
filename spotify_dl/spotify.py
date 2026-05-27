from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from spotify_dl.auth import USER_SCOPES, build_spotify_oauth
from spotify_dl.config import ConfigManager
from spotify_dl.cover_art import CoverResolver
from spotify_dl.exceptions import SpotifyError
from spotify_dl.models import AppConfig, PlaylistSummary, TrackMetadata
from spotify_dl.source_cache import CoverCache, SourceCache


SPOTIFY_URL_RE = re.compile(
    r"https?://open\.spotify\.com/(?P<kind>track|album|playlist)/(?P<id>[A-Za-z0-9]+)"
)
SPOTIFY_URI_RE = re.compile(
    r"spotify:(?P<kind>track|album|playlist):(?P<id>[A-Za-z0-9]+)"
)


def parse_spotify_url(url: str) -> tuple[Literal["track", "album", "playlist"], str]:
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


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


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
        auth_manager = SpotifyClientCredentials(
            client_id=config.spotify_client_id,
            client_secret=config.spotify_client_secret,
        )
        self.client = spotipy.Spotify(auth_manager=auth_manager, requests_timeout=20, retries=3)
        _cache_dir = (cache_dir or Path.home() / ".spotify-dl" / "cache").expanduser()
        self.source_cache = SourceCache(_cache_dir)
        self.cover_cache = CoverCache(_cache_dir)
        self.cover_resolver = CoverResolver(self.cover_cache)

    def resolve_url(self, url: str) -> tuple[str, str, list[TrackMetadata]]:
        kind, item_id = parse_spotify_url(url)
        if kind == "track":
            track = self.get_track(item_id)
            return kind, track.title, [track]
        if kind == "album":
            tracks = self.get_album(item_id)
            self._prefetch_covers(tracks)
            name = tracks[0].album_name if tracks else "Album"
            return kind, name, tracks
        header = self.get_playlist_header(item_id)
        tracks = self.get_playlist(
            item_id,
            snapshot_id=header.get("snapshot_id"),
            playlist_name=header.get("name"),
        )
        self._prefetch_covers(tracks)
        return kind, header["name"], tracks

    def get_track(self, track_id: str) -> TrackMetadata:
        try:
            return track_from_spotify(self.client.track(track_id))
        except Exception as exc:
            raise SpotifyError(f"Track not found on Spotify: {track_id}") from exc

    def get_album(self, album_id: str) -> list[TrackMetadata]:
        cached = self.source_cache.load(kind="album", source_id=album_id)
        if cached:
            return cached[1]
        try:
            album = self.client.album(album_id)
            tracks = list(_iter_page_items(self.client, album["tracks"]))
            full_tracks = [self.client.track(track["id"]) for track in tracks if track.get("id")]
            metadata = [track_from_spotify(track, album) for track in full_tracks]
            self.source_cache.save(
                kind="album",
                source_id=album_id,
                source_name=album.get("name") or album_id,
                tracks=metadata,
            )
            return metadata
        except Exception as exc:
            raise SpotifyError(f"Album not found on Spotify: {album_id}") from exc

    def get_playlist_header(self, playlist_id: str) -> dict[str, Any]:
        client = self._playlist_client()
        return client.playlist(playlist_id, fields="id,name,snapshot_id,tracks(total),external_urls")

    def get_playlist(
        self,
        playlist_id: str,
        *,
        snapshot_id: str | None = None,
        playlist_name: str | None = None,
    ) -> list[TrackMetadata]:
        try:
            client = self._playlist_client()
            if snapshot_id is None or playlist_name is None:
                header = self.get_playlist_header(playlist_id)
                snapshot_id = header.get("snapshot_id")
                playlist_name = header.get("name")
            cached = self.source_cache.load(
                kind="playlist",
                source_id=playlist_id,
                snapshot_id=snapshot_id,
            )
            if cached:
                return cached[1]
            page = client.playlist_items(playlist_id, limit=100, offset=0)
            tracks: list[TrackMetadata] = []
            for item in _iter_page_items(client, page):
                track = (item.get("track") or item.get("item")) if item else None
                if (
                    not track
                    or track.get("type") != "track"
                    or not track.get("id")
                    or track.get("is_local")
                ):
                    continue
                tracks.append(track_from_spotify(track))
            self.source_cache.save(
                kind="playlist",
                source_id=playlist_id,
                source_name=playlist_name or playlist_id,
                snapshot_id=snapshot_id,
                tracks=tracks,
            )
            return tracks
        except SpotifyError:
            raise
        except Exception as exc:
            raise SpotifyError(f"Playlist not found on Spotify: {playlist_id}") from exc

    def _prefetch_covers(self, tracks: list[TrackMetadata]) -> None:
        self.cover_resolver.prefetch(tracks)

    def get_tracks(self, track_ids: list[str], client: spotipy.Spotify | None = None) -> list[TrackMetadata]:
        spotify_client = client or self.client
        tracks: list[TrackMetadata] = []
        for chunk in _chunks(track_ids, 50):
            response = spotify_client.tracks(chunk)
            tracks.extend(
                track_from_spotify(track)
                for track in response.get("tracks", [])
                if track and track.get("id")
            )
        return tracks

    def list_user_playlists(self) -> list[PlaylistSummary]:
        user = self._user_client()
        playlists: list[PlaylistSummary] = []
        page = user.current_user_playlists(limit=50)
        for item in _iter_page_items(user, page):
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

    def get_playlist_track_count(self, playlist_id: str) -> int:
        user = self._user_client()
        try:
            page = user.playlist_items(playlist_id, limit=1, offset=0, fields="total")
            return int(page.get("total") or 0)
        except Exception:
            pass
        try:
            header = user.playlist(playlist_id, fields="tracks(total)")
            return int(((header.get("tracks") or {}).get("total")) or 0)
        except Exception:
            return 0

    def _user_client(self) -> spotipy.Spotify:
        if token_expires_soon(self.config.spotify_user_token_expiry):
            self._refresh_user_token()
        if not self.config.spotify_user_access_token:
            raise SpotifyError("Run spotify-dl auth login first")
        return spotipy.Spotify(auth=self.config.spotify_user_access_token)

    def _playlist_client(self) -> spotipy.Spotify:
        if self.config.spotify_user_access_token or self.config.spotify_user_refresh_token:
            return self._user_client()
        return self.client

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


def token_expires_soon(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    return expires_at <= datetime.now(timezone.utc) + timedelta(minutes=5)
