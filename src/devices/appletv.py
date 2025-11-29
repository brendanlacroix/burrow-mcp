"""AppleTV device implementation for Burrow MCP.

Uses the pyatv library for local control and state monitoring.
https://pyatv.dev/
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from config import DeviceConfig, SecretsConfig
from models.base import DeviceStatus, DeviceType
from models.media_device import (
    MediaDevice,
    NowPlaying,
    PlaybackState,
    normalize_app_name,
)
from utils.retry import CircuitBreaker, CircuitBreakerOpen, retry_async

logger = logging.getLogger(__name__)

# Circuit breaker for AppleTV operations (shared across all AppleTV devices)
_appletv_circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60.0,
    half_open_max_calls=2,
)

# Map pyatv device states to our PlaybackState
PYATV_STATE_MAP = {
    "idle": PlaybackState.IDLE,
    "playing": PlaybackState.PLAYING,
    "paused": PlaybackState.PAUSED,
    "loading": PlaybackState.LOADING,
    "stopped": PlaybackState.STOPPED,
    "seeking": PlaybackState.PLAYING,
}


@dataclass
class AppleTVDevice(MediaDevice):
    """AppleTV implementation using pyatv library.

    Connects to AppleTV on the local network and provides:
    - Playback state monitoring
    - Currently playing content info
    - Remote control (play, pause, skip)
    - App launching
    - Viewing history tracking (via periodic polling)
    """

    device_type: DeviceType = field(default=DeviceType.MEDIA, init=False)
    _ip: str | None = None
    _identifier: str | None = None  # AppleTV unique ID
    _atv: Any = field(default=None, repr=False)  # pyatv AppleTV instance
    _connected: bool = False
    _push_listener: Any = field(default=None, repr=False)
    _last_content_hash: str | None = None  # Track content changes

    async def _run_with_retry(self, coro: Any) -> Any:
        """Run an async operation with retry and circuit breaker."""
        if _appletv_circuit_breaker.is_open:
            raise CircuitBreakerOpen("AppleTV circuit breaker is open")

        try:
            result = await retry_async(
                lambda: coro,
                max_attempts=3,
                initial_delay=0.5,
                max_delay=5.0,
                retryable_exceptions=(OSError, TimeoutError, ConnectionError),
            )
            _appletv_circuit_breaker.record_success()
            return result
        except Exception:
            _appletv_circuit_breaker.record_failure()
            raise

    async def _ensure_connected(self) -> bool:
        """Ensure connection to AppleTV."""
        if self._atv is None:
            logger.debug(f"AppleTV {self.id} not initialized")
            return False

        if not self._connected:
            try:
                # pyatv handles reconnection internally
                self._connected = True
                logger.info(f"Connected to AppleTV {self.id}")
            except CircuitBreakerOpen:
                logger.warning(f"Circuit breaker open for AppleTV {self.id}")
                return False
            except Exception as e:
                logger.error(f"Failed to connect to AppleTV {self.id}: {e}")
                return False

        return True

    def _get_content_hash(self) -> str | None:
        """Generate a hash of current content for change detection."""
        if not self.now_playing:
            return None
        np = self.now_playing
        return f"{np.app}:{np.title}:{np.series_name}:{np.season}:{np.episode}"

    async def refresh(self) -> None:
        """Fetch current state from AppleTV."""
        if not await self._ensure_connected():
            self.status = DeviceStatus.OFFLINE
            return

        try:
            # Get playing status
            playing = self._atv.metadata.playing

            if playing:
                # Map device state
                state_str = str(playing.device_state).lower().split(".")[-1]
                self.playback_state = PYATV_STATE_MAP.get(
                    state_str, PlaybackState.IDLE
                )

                # Get current app
                app_info = self._atv.metadata.app
                if app_info:
                    self.current_app = normalize_app_name(app_info.identifier or app_info.name or "Unknown")
                else:
                    self.current_app = None

                # Build now playing info
                self.now_playing = NowPlaying(
                    title=playing.title,
                    artist=playing.artist,
                    album=playing.album,
                    series_name=playing.series_name,
                    season=playing.season_number,
                    episode=playing.episode_number,
                    genre=playing.genre,
                    media_type=self._determine_media_type(playing),
                    app=self.current_app,
                    duration=playing.total_time,
                    position=playing.position,
                )

                self.status = DeviceStatus.ONLINE
                logger.debug(
                    f"Refreshed AppleTV {self.id}: state={self.playback_state.value}, "
                    f"app={self.current_app}, title={playing.title}"
                )
            else:
                self.playback_state = PlaybackState.IDLE
                self.now_playing = None
                self.status = DeviceStatus.ONLINE

        except CircuitBreakerOpen:
            logger.warning(f"Circuit breaker open for AppleTV {self.id}")
            self.status = DeviceStatus.OFFLINE
        except Exception as e:
            logger.error(f"Failed to refresh AppleTV {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE

    def _determine_media_type(self, playing: Any) -> str:
        """Determine if content is a movie, TV show, or music."""
        # Check for TV show indicators
        if playing.series_name or playing.season_number or playing.episode_number:
            return "tvshow"

        # Check for music indicators
        if playing.artist and playing.album:
            return "music"

        # Check media type from pyatv if available
        if hasattr(playing, "media_type"):
            mt = str(playing.media_type).lower()
            if "tv" in mt or "video" in mt:
                return "tvshow" if playing.series_name else "movie"
            if "music" in mt or "audio" in mt:
                return "music"

        return "unknown"

    async def play(self) -> None:
        """Resume/start playback."""
        if not await self._ensure_connected():
            raise RuntimeError(f"AppleTV {self.id} not connected")

        try:
            await self._run_with_retry(self._atv.remote_control.play())
            self.playback_state = PlaybackState.PLAYING
            self.status = DeviceStatus.ONLINE
            logger.info(f"Started playback on AppleTV {self.id}")

        except CircuitBreakerOpen:
            self.status = DeviceStatus.OFFLINE
            raise RuntimeError(f"AppleTV {self.id} temporarily unavailable")
        except Exception as e:
            logger.error(f"Failed to play on AppleTV {self.id}: {e}")
            raise

    async def pause(self) -> None:
        """Pause playback."""
        if not await self._ensure_connected():
            raise RuntimeError(f"AppleTV {self.id} not connected")

        try:
            await self._run_with_retry(self._atv.remote_control.pause())
            self.playback_state = PlaybackState.PAUSED
            self.status = DeviceStatus.ONLINE
            logger.info(f"Paused playback on AppleTV {self.id}")

        except CircuitBreakerOpen:
            self.status = DeviceStatus.OFFLINE
            raise RuntimeError(f"AppleTV {self.id} temporarily unavailable")
        except Exception as e:
            logger.error(f"Failed to pause AppleTV {self.id}: {e}")
            raise

    async def stop(self) -> None:
        """Stop playback."""
        if not await self._ensure_connected():
            raise RuntimeError(f"AppleTV {self.id} not connected")

        try:
            await self._run_with_retry(self._atv.remote_control.stop())
            self.playback_state = PlaybackState.STOPPED
            self.now_playing = None
            self.status = DeviceStatus.ONLINE
            logger.info(f"Stopped playback on AppleTV {self.id}")

        except CircuitBreakerOpen:
            self.status = DeviceStatus.OFFLINE
            raise RuntimeError(f"AppleTV {self.id} temporarily unavailable")
        except Exception as e:
            logger.error(f"Failed to stop AppleTV {self.id}: {e}")
            raise

    async def skip_forward(self) -> None:
        """Skip to next track/episode."""
        if not await self._ensure_connected():
            raise RuntimeError(f"AppleTV {self.id} not connected")

        try:
            await self._run_with_retry(self._atv.remote_control.next())
            self.status = DeviceStatus.ONLINE
            logger.info(f"Skipped forward on AppleTV {self.id}")

        except CircuitBreakerOpen:
            self.status = DeviceStatus.OFFLINE
            raise RuntimeError(f"AppleTV {self.id} temporarily unavailable")
        except Exception as e:
            logger.error(f"Failed to skip forward on AppleTV {self.id}: {e}")
            raise

    async def skip_backward(self) -> None:
        """Skip to previous track/episode."""
        if not await self._ensure_connected():
            raise RuntimeError(f"AppleTV {self.id} not connected")

        try:
            await self._run_with_retry(self._atv.remote_control.previous())
            self.status = DeviceStatus.ONLINE
            logger.info(f"Skipped backward on AppleTV {self.id}")

        except CircuitBreakerOpen:
            self.status = DeviceStatus.OFFLINE
            raise RuntimeError(f"AppleTV {self.id} temporarily unavailable")
        except Exception as e:
            logger.error(f"Failed to skip backward on AppleTV {self.id}: {e}")
            raise

    async def launch_app(self, app_id: str) -> None:
        """Launch a specific app."""
        if not await self._ensure_connected():
            raise RuntimeError(f"AppleTV {self.id} not connected")

        try:
            # Find matching app from available apps
            apps = await self.get_app_list()
            matching_app = None

            for app in apps:
                if app_id.lower() in app.get("name", "").lower() or \
                   app_id.lower() == app.get("id", "").lower():
                    matching_app = app
                    break

            if not matching_app:
                raise ValueError(f"App '{app_id}' not found on AppleTV {self.id}")

            await self._run_with_retry(
                self._atv.apps.launch_app(matching_app["id"])
            )
            self.current_app = normalize_app_name(matching_app["name"])
            self.status = DeviceStatus.ONLINE
            logger.info(f"Launched {matching_app['name']} on AppleTV {self.id}")

        except CircuitBreakerOpen:
            self.status = DeviceStatus.OFFLINE
            raise RuntimeError(f"AppleTV {self.id} temporarily unavailable")
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"Failed to launch app on AppleTV {self.id}: {e}")
            raise

    async def get_app_list(self) -> list[dict[str, str]]:
        """Get list of installed apps."""
        if not await self._ensure_connected():
            return []

        try:
            app_list = await self._run_with_retry(self._atv.apps.app_list())

            apps = []
            for app in app_list:
                apps.append({
                    "id": app.identifier,
                    "name": app.name,
                    "friendly_name": normalize_app_name(app.identifier or app.name),
                })

            # Update available apps list
            self.available_apps = [a["friendly_name"] for a in apps]

            return apps

        except CircuitBreakerOpen:
            logger.warning(f"Circuit breaker open for AppleTV {self.id}")
            return []
        except Exception as e:
            logger.error(f"Failed to get app list from AppleTV {self.id}: {e}")
            return []

    async def close(self) -> None:
        """Close connection to AppleTV."""
        if self._atv:
            try:
                self._atv.close()
                self._connected = False
                logger.info(f"Closed connection to AppleTV {self.id}")
            except Exception as e:
                logger.warning(f"Error closing AppleTV {self.id}: {e}")

    async def reconnect(self) -> None:
        """Attempt to reconnect to AppleTV."""
        _appletv_circuit_breaker.reset()
        self._connected = False
        await self.close()

        # Attempt to rediscover and connect
        try:
            import pyatv

            if self._ip:
                atvs = await pyatv.scan(hosts=[self._ip], timeout=10)
            elif self._identifier:
                atvs = await pyatv.scan(identifier=self._identifier, timeout=10)
            else:
                logger.error(f"No IP or identifier for AppleTV {self.id}")
                return

            if atvs:
                self._atv = await pyatv.connect(atvs[0], asyncio.get_event_loop())
                await self.refresh()
                logger.info(f"Reconnected to AppleTV {self.id}")
            else:
                logger.warning(f"Could not find AppleTV {self.id} on network")
                self.status = DeviceStatus.OFFLINE

        except Exception as e:
            logger.error(f"Failed to reconnect to AppleTV {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE


async def create_appletv_device(
    device_config: DeviceConfig, secrets: SecretsConfig
) -> AppleTVDevice:
    """Factory function to create an AppleTV device from config.

    Configuration options:
    - ip: IP address of the AppleTV (preferred for direct connection)
    - identifier: AppleTV unique ID (for discovery-based connection)

    Credentials in secrets.yaml:
    - appletv.<device_id>.credentials: Pairing credentials (optional, will prompt if needed)
    """
    try:
        import pyatv
    except ImportError:
        logger.error("pyatv package not installed. Install with: pip install pyatv")
        return AppleTVDevice(
            id=device_config.id,
            name=device_config.name,
            room_id=device_config.room,
        )

    ip = device_config.config.get("ip")
    identifier = device_config.config.get("identifier")

    device = AppleTVDevice(
        id=device_config.id,
        name=device_config.name,
        room_id=device_config.room,
        _ip=ip,
        _identifier=identifier,
    )

    if not ip and not identifier:
        logger.warning(
            f"AppleTV {device_config.id} has no IP or identifier. "
            "Use 'atvremote scan' to find your AppleTV."
        )
        return device

    try:
        # Scan for the device
        if ip:
            atvs = await pyatv.scan(hosts=[ip], timeout=10)
        else:
            atvs = await pyatv.scan(identifier=identifier, timeout=10)

        if not atvs:
            logger.warning(f"AppleTV {device_config.id} not found on network")
            return device

        atv_conf = atvs[0]

        # Check for stored credentials
        device_secrets = getattr(secrets, "appletv", {}).get(device_config.id, {})
        credentials = device_secrets.get("credentials")

        if credentials:
            # Apply stored credentials
            for protocol, cred in credentials.items():
                atv_conf.set_credentials(pyatv.Protocol[protocol.upper()], cred)

        # Connect to AppleTV
        device._atv = await pyatv.connect(atv_conf, asyncio.get_event_loop())
        device._connected = True
        device._identifier = atv_conf.identifier

        # Get initial state
        await device.refresh()

        # Get app list
        await device.get_app_list()

        logger.info(
            f"Created AppleTV {device_config.id} at {ip or identifier} "
            f"(apps: {', '.join(device.available_apps[:5])}...)"
        )

    except Exception as e:
        logger.warning(f"Failed to connect to AppleTV {device_config.id}: {e}")
        device.status = DeviceStatus.OFFLINE

    return device


async def discover_appletv(timeout: float = 10.0) -> list[dict[str, Any]]:
    """Discover AppleTV devices on the network.

    Returns list of discovered devices with their IP, name, and identifier.
    Use these values in your config.yaml to set up the device.
    """
    try:
        import pyatv
    except ImportError:
        logger.error("pyatv package not installed")
        return []

    logger.info(f"Scanning for AppleTV devices ({timeout}s)...")

    try:
        atvs = await pyatv.scan(timeout=timeout)

        results = []
        for atv in atvs:
            results.append({
                "ip": str(atv.address),
                "name": atv.name,
                "identifier": atv.identifier,
                "device_info": str(atv.device_info) if atv.device_info else None,
            })
            logger.info(f"Found AppleTV: {atv.name} at {atv.address}")

        return results

    except Exception as e:
        logger.error(f"AppleTV discovery failed: {e}")
        return []
