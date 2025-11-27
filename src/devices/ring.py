"""Ring camera implementation for Burrow MCP.

Uses the ring-doorbell library for Ring device access.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from config import DeviceConfig, SecretsConfig
from models.base import DeviceStatus, DeviceType
from models.camera import Camera

logger = logging.getLogger(__name__)

# Token cache file location
TOKEN_CACHE_PATH = Path.home() / ".cache" / "burrow" / "ring_token.json"


@dataclass
class RingCamera(Camera):
    """Ring camera/doorbell implementation using ring-doorbell library."""

    device_type: DeviceType = field(default=DeviceType.CAMERA, init=False)
    _device_id: str | None = None
    _ring: Any = field(default=None, repr=False)
    _device: Any = field(default=None, repr=False)
    battery_percent: int | None = None
    has_subscription: bool = False
    firmware_version: str | None = None
    wifi_signal_strength: int | None = None

    async def refresh(self) -> None:
        """Fetch current state from Ring cloud."""
        if not self._device:
            self.status = DeviceStatus.OFFLINE
            return

        try:
            # ring-doorbell is synchronous, run in thread
            await asyncio.to_thread(self._device.update)

            # Get device health info
            health = await asyncio.to_thread(self._device.update_health_data)

            # Update battery if available (doorbells and some cameras)
            if hasattr(self._device, "battery_life"):
                self.battery_percent = self._device.battery_life

            # WiFi signal strength
            if health and hasattr(self._device, "wifi_signal_strength"):
                self.wifi_signal_strength = self._device.wifi_signal_strength

            # Firmware version
            if hasattr(self._device, "firmware"):
                self.firmware_version = self._device.firmware

            # Get last motion event
            try:
                history = await asyncio.to_thread(
                    self._device.history, limit=1, kind="motion"
                )
                if history:
                    event = history[0]
                    # Ring returns datetime objects
                    if isinstance(event.get("created_at"), datetime):
                        self.last_motion = event["created_at"].isoformat()
                    else:
                        self.last_motion = str(event.get("created_at"))
            except Exception as e:
                logger.debug(f"Could not get motion history for {self.id}: {e}")

            # Get last ding event (for doorbells)
            try:
                history = await asyncio.to_thread(
                    self._device.history, limit=1, kind="ding"
                )
                if history:
                    event = history[0]
                    if isinstance(event.get("created_at"), datetime):
                        self.last_ding = event["created_at"].isoformat()
                    else:
                        self.last_ding = str(event.get("created_at"))
            except Exception as e:
                logger.debug(f"Could not get ding history for {self.id}: {e}")

            self.status = DeviceStatus.ONLINE
            logger.debug(
                f"Refreshed Ring {self.id}: battery={self.battery_percent}%, "
                f"last_motion={self.last_motion}"
            )

        except Exception as e:
            logger.error(f"Failed to refresh Ring camera {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE

    async def get_snapshot_url(self) -> str | None:
        """Get URL for the most recent snapshot.

        Note: Requires Ring Protect subscription.
        """
        if not self._device:
            return None

        try:
            # Request a new snapshot
            await asyncio.to_thread(self._device.get_snapshot)

            # Wait a moment for it to be ready
            await asyncio.sleep(2)

            # Get the snapshot URL
            snapshot = await asyncio.to_thread(self._device.recording_url, None)
            return snapshot

        except Exception as e:
            logger.error(f"Failed to get snapshot for {self.id}: {e}")
            return None

    async def get_last_video_url(self) -> str | None:
        """Get URL for the most recent recording.

        Note: Requires Ring Protect subscription.
        """
        if not self._device:
            return None

        try:
            history = await asyncio.to_thread(self._device.history, limit=1)
            if history:
                event = history[0]
                url = await asyncio.to_thread(
                    self._device.recording_url, event["id"]
                )
                return url
            return None

        except Exception as e:
            logger.error(f"Failed to get video URL for {self.id}: {e}")
            return None

    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict."""
        state = super().to_state_dict()
        state.update({
            "battery_percent": self.battery_percent,
            "has_subscription": self.has_subscription,
            "wifi_signal_strength": self.wifi_signal_strength,
            "firmware_version": self.firmware_version,
        })
        return state


def _token_updated_callback(token: dict) -> None:
    """Callback when Ring token is updated."""
    TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE_PATH.write_text(json.dumps(token))
    logger.debug("Ring token updated and cached")


def _load_cached_token() -> dict | None:
    """Load cached Ring token if available."""
    if TOKEN_CACHE_PATH.exists():
        try:
            return json.loads(TOKEN_CACHE_PATH.read_text())
        except Exception as e:
            logger.warning(f"Failed to load Ring token cache: {e}")
    return None


async def create_ring_camera(
    device_config: DeviceConfig, secrets: SecretsConfig
) -> RingCamera:
    """Factory function to create a Ring camera from config.

    Ring authentication requires either:
    1. A cached token from previous authentication
    2. Username/password with 2FA code (interactive)

    For non-interactive use, run the authentication once interactively
    to cache the token.
    """
    try:
        from ring_doorbell import Auth, Ring
    except ImportError:
        logger.error(
            "ring-doorbell package not installed. Install with: pip install ring-doorbell"
        )
        return RingCamera(
            id=device_config.id,
            name=device_config.name,
            room_id=device_config.room,
        )

    device_id = secrets.ring.get("device_id") or device_config.config.get("device_id")
    username = secrets.ring.get("username")
    password = secrets.ring.get("password")
    refresh_token = secrets.ring.get("refresh_token")

    camera = RingCamera(
        id=device_config.id,
        name=device_config.name,
        room_id=device_config.room,
        _device_id=device_id,
    )

    # Try to load cached token
    cached_token = _load_cached_token()

    try:
        # First try cached token
        if cached_token:
            try:
                auth = Auth("BurrowMCP/1.0", cached_token, _token_updated_callback)
                ring = Ring(auth)
                await asyncio.to_thread(ring.update_data)
                camera._ring = ring
                logger.info(f"Ring {device_config.id}: Authenticated with cached token")
            except Exception as e:
                logger.warning(f"Cached Ring token failed: {e}")
                cached_token = None

        # Try refresh token from secrets
        if not cached_token and refresh_token:
            try:
                token = {"refresh_token": refresh_token}
                auth = Auth("BurrowMCP/1.0", token, _token_updated_callback)
                ring = Ring(auth)
                await asyncio.to_thread(ring.update_data)
                camera._ring = ring
                logger.info(f"Ring {device_config.id}: Authenticated with refresh token")
            except Exception as e:
                logger.warning(f"Ring refresh token failed: {e}")

        # Try username/password (requires 2FA, so mainly for setup)
        if not camera._ring and username and password:
            logger.warning(
                f"Ring {device_config.id}: Username/password authentication "
                "requires 2FA. Run interactive setup first to cache token."
            )

        if not camera._ring:
            logger.warning(
                f"Ring {device_config.id}: No valid authentication. "
                "Run 'burrow discover ring' for setup instructions."
            )
            return camera

        # Find the specific device
        if device_id:
            # Look through all Ring devices
            for device_type in [camera._ring.doorbells, camera._ring.stickup_cams]:
                devices = await asyncio.to_thread(lambda: list(device_type()))
                for device in devices:
                    if str(device.id) == device_id or device.name == device_id:
                        camera._device = device
                        camera.has_subscription = getattr(
                            device, "has_subscription", False
                        )
                        logger.info(
                            f"Ring {device_config.id}: Found device '{device.name}'"
                        )
                        break
                if camera._device:
                    break

            if not camera._device:
                logger.warning(
                    f"Ring {device_config.id}: Device '{device_id}' not found. "
                    "Run 'burrow discover ring' to list available devices."
                )
        else:
            logger.warning(
                f"Ring {device_config.id}: No device_id specified. "
                "Run 'burrow discover ring' to list available devices."
            )

        # Try initial refresh
        if camera._device:
            try:
                await camera.refresh()
            except Exception as e:
                logger.warning(f"Initial refresh failed for Ring {device_config.id}: {e}")

    except Exception as e:
        logger.error(f"Failed to initialize Ring camera {device_config.id}: {e}")

    return camera


async def list_ring_devices(secrets: SecretsConfig) -> list[dict[str, Any]]:
    """List all Ring devices associated with the account.

    Args:
        secrets: Secrets config with Ring credentials

    Returns:
        List of device info dicts
    """
    try:
        from ring_doorbell import Auth, Ring
    except ImportError:
        logger.error("ring-doorbell package not installed")
        return []

    refresh_token = secrets.ring.get("refresh_token")

    # Try cached token first
    cached_token = _load_cached_token()

    ring = None

    if cached_token:
        try:
            auth = Auth("BurrowMCP/1.0", cached_token, _token_updated_callback)
            ring = Ring(auth)
            await asyncio.to_thread(ring.update_data)
        except Exception as e:
            logger.warning(f"Cached Ring token failed: {e}")
            ring = None

    if not ring and refresh_token:
        try:
            token = {"refresh_token": refresh_token}
            auth = Auth("BurrowMCP/1.0", token, _token_updated_callback)
            ring = Ring(auth)
            await asyncio.to_thread(ring.update_data)
        except Exception as e:
            logger.error(f"Ring authentication failed: {e}")
            return []

    if not ring:
        logger.error(
            "Ring authentication required. Run 'burrow discover ring' for setup."
        )
        return []

    results = []

    # Get doorbells
    doorbells = await asyncio.to_thread(lambda: list(ring.doorbells()))
    for device in doorbells:
        results.append({
            "device_id": str(device.id),
            "name": device.name,
            "type": "doorbell",
            "model": getattr(device, "model", "unknown"),
            "battery": getattr(device, "battery_life", None),
            "has_subscription": getattr(device, "has_subscription", False),
        })
        logger.info(f"Found Ring doorbell: {device.name} ({device.id})")

    # Get cameras (stickup cams, spotlights, floodlights)
    cameras = await asyncio.to_thread(lambda: list(ring.stickup_cams()))
    for device in cameras:
        results.append({
            "device_id": str(device.id),
            "name": device.name,
            "type": "camera",
            "model": getattr(device, "model", "unknown"),
            "battery": getattr(device, "battery_life", None),
            "has_subscription": getattr(device, "has_subscription", False),
        })
        logger.info(f"Found Ring camera: {device.name} ({device.id})")

    # Get chimes
    chimes = await asyncio.to_thread(lambda: list(ring.chimes()))
    for device in chimes:
        results.append({
            "device_id": str(device.id),
            "name": device.name,
            "type": "chime",
            "model": getattr(device, "model", "unknown"),
        })
        logger.info(f"Found Ring chime: {device.name} ({device.id})")

    return results


async def authenticate_ring_interactive(username: str, password: str) -> dict | None:
    """Interactively authenticate with Ring (requires 2FA).

    This function will prompt for 2FA code. After successful authentication,
    the token is cached for future use.

    Args:
        username: Ring account email
        password: Ring account password

    Returns:
        Token dict if successful, None otherwise
    """
    try:
        from ring_doorbell import Auth
    except ImportError:
        logger.error("ring-doorbell package not installed")
        return None

    print("Ring Authentication")
    print("=" * 40)
    print()
    print("Ring requires 2-factor authentication.")
    print("You will receive a code via email or SMS.")
    print()

    try:
        auth = Auth("BurrowMCP/1.0", None, _token_updated_callback)

        # This will trigger 2FA
        await asyncio.to_thread(auth.fetch_token, username, password)

        # Prompt for 2FA code
        code = input("Enter 2FA code: ").strip()

        await asyncio.to_thread(auth.fetch_token, username, password, code)

        # If successful, token should be cached via callback
        logger.info("Ring authentication successful!")
        print()
        print("✓ Authentication successful!")
        print(f"✓ Token cached at: {TOKEN_CACHE_PATH}")
        print()
        print("You can now use Ring devices in burrow-mcp.")

        return _load_cached_token()

    except Exception as e:
        logger.error(f"Ring authentication failed: {e}")
        print(f"✗ Authentication failed: {e}")
        return None
