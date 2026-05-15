class SpotifyDlError(Exception):
    """Base exception for user-facing spotify-dl failures."""


class ConfigError(SpotifyDlError):
    """Raised when configuration is missing or invalid."""


class SpotifyError(SpotifyDlError):
    """Raised when Spotify API access fails."""


class YouTubeMatchError(SpotifyDlError):
    """Raised when no suitable YouTube match can be found."""


class DownloadError(SpotifyDlError):
    """Raised when a download or conversion fails."""


class TaggingError(SpotifyDlError):
    """Raised when ID3 tagging fails."""




