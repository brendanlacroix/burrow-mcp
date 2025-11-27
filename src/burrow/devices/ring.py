"""Ring camera implementation for Burrow MCP."""

import logging
from dataclasses import dataclass, field
from typing import Any

from burrow.config import DeviceConfig, SecretsConfig
from burrow.models.device import Device, DeviceStatus, DeviceType

logger = logging.getLogger(__name__)


@dataclass
class RingCamera(Device):
    """Ring camera implementation."""

    device_type: DeviceType = field(default=DeviceType.CAMERA, init=False)
    _device_id: str | None = None
    _api: Any = field(default=None, repr=False)
    last_motion: str | None = None
    last_ding: str | None = None

    async def refresh(self) -> None:
        """Fetch current state from Ring cloud."""
        # TODO: Implement Ring API state refresh
        logger.warning(f"Ring refresh not yet implemented for {self.id}")
        self.status = DeviceStatus.UNKNOWN

    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict."""
        return {
            "last_motion": self.last_motion,
            "last_ding": self.last_ding,
        }


async def create_ring_camera(device_config: DeviceConfig, secrets: SecretsConfig) -> RingCamera:
    """Factory function to create a Ring camera from config.

    Args:
        device_config: Device configuration
        secrets: Secrets configuration containing Ring credentials

    Returns:
        Configured RingCamera instance
    """
    camera = RingCamera(
        id=device_config.id,
        name=device_config.name,
        room_id=device_config.room,
        _device_id=device_config.config.get("device_id"),
    )

    return camera
