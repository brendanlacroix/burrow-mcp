"""Media device models for Burrow MCP."""

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from models.base import Device, DeviceType


class PlaybackState(Enum):
    """Media playback states."""

    IDLE = "idle"
    PLAYING = "playing"
    PAUSED = "paused"
    LOADING = "loading"
    STOPPED = "stopped"


@dataclass
class NowPlaying:
    """Information about currently playing content."""

    title: str | None = None
    artist: str | None = None  # For music
    album: str | None = None  # For music
    series_name: str | None = None  # For TV shows
    season: int | None = None  # For TV shows
    episode: int | None = None  # For TV shows
    genre: str | None = None
    media_type: str | None = None  # "movie", "tvshow", "music", "unknown"
    app: str | None = None  # Source app (Netflix, Hulu, etc.)
    duration: int | None = None  # Total duration in seconds
    position: int | None = None  # Current position in seconds

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        return {k: v for k, v in {
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "series_name": self.series_name,
            "season": self.season,
            "episode": self.episode,
            "genre": self.genre,
            "media_type": self.media_type,
            "app": self.app,
            "duration": self.duration,
            "position": self.position,
        }.items() if v is not None}


@dataclass
class MediaDevice(Device):
    """Base class for media devices (AppleTV, Roku, etc.).

    Provides:
    - Playback state tracking
    - Current content information
    - App management
    - Viewing history integration
    """

    device_type: DeviceType = field(default=DeviceType.MEDIA, init=False)
    playback_state: PlaybackState = PlaybackState.IDLE
    now_playing: NowPlaying | None = None
    current_app: str | None = None
    available_apps: list[str] = field(default_factory=list)
    volume: int | None = None  # 0-100 if available

    @abstractmethod
    async def play(self) -> None:
        """Resume/start playback."""
        pass

    @abstractmethod
    async def pause(self) -> None:
        """Pause playback."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop playback."""
        pass

    @abstractmethod
    async def skip_forward(self) -> None:
        """Skip forward (next track/episode)."""
        pass

    @abstractmethod
    async def skip_backward(self) -> None:
        """Skip backward (previous track/episode)."""
        pass

    @abstractmethod
    async def launch_app(self, app_id: str) -> None:
        """Launch a specific app."""
        pass

    @abstractmethod
    async def get_app_list(self) -> list[dict[str, str]]:
        """Get list of installed apps."""
        pass

    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict for MCP responses."""
        state = {
            "playback_state": self.playback_state.value,
            "current_app": self.current_app,
        }

        if self.now_playing:
            state["now_playing"] = self.now_playing.to_dict()

        if self.available_apps:
            state["available_apps"] = self.available_apps

        if self.volume is not None:
            state["volume"] = self.volume

        return state


# Common streaming service identifiers
# These help normalize app names across different platforms
STREAMING_SERVICES = {
    # Netflix
    "com.netflix.Netflix": "Netflix",
    "netflix": "Netflix",
    # Hulu
    "com.hulu.plus": "Hulu",
    "hulu": "Hulu",
    # Disney+
    "com.disney.disneyplus": "Disney+",
    "disney+": "Disney+",
    "disneyplus": "Disney+",
    # HBO Max / Max
    "com.hbo.hbonow": "Max",
    "com.wbd.stream": "Max",
    "hbomax": "Max",
    "max": "Max",
    # Amazon Prime Video
    "com.amazon.aiv.AIVApp": "Prime Video",
    "primevideo": "Prime Video",
    "amazon": "Prime Video",
    # Apple TV+
    "com.apple.TVWatchList": "Apple TV+",
    "tvapp": "Apple TV+",
    # Peacock
    "com.peacocktv.peacockios": "Peacock",
    "peacock": "Peacock",
    # Paramount+
    "com.cbs.app": "Paramount+",
    "paramount+": "Paramount+",
    # YouTube
    "com.google.ios.youtube": "YouTube",
    "youtube": "YouTube",
    # YouTube TV
    "com.google.ios.youtubeunplugged": "YouTube TV",
    "youtubetv": "YouTube TV",
    # Plex
    "com.plexapp.plex": "Plex",
    "plex": "Plex",
    # Spotify (audio but common)
    "com.spotify.client": "Spotify",
    "spotify": "Spotify",
}


def normalize_app_name(app_id: str) -> str:
    """Normalize an app identifier to a friendly name."""
    # Check our mapping first
    if app_id in STREAMING_SERVICES:
        return STREAMING_SERVICES[app_id]

    # Try lowercase
    lower = app_id.lower()
    if lower in STREAMING_SERVICES:
        return STREAMING_SERVICES[lower]

    # Return as-is if not found
    return app_id
