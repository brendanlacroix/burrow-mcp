"""Ring camera implementation for Burrow MCP."""

import logging
from dataclasses import dataclass, field
from typing import Any

from config import DeviceConfig, SecretsConfig
from models.base import DeviceStatus, DeviceType
from models.camera import Camera

logger = logging.getLogger(__name__)


@dataclass
class RingCamera(Camera):
    """Ring camera implementation."""

    device_type: DeviceType = field(default=DeviceType.CAMERA, init=False)
    _device_id: str | None = None
    _api: Any = field(default=None, repr=False)

    async def refresh(self) -> None:
        """Fetch current state from Ring cloud."""
        # TODO: Implement Ring API state refresh
        logger.warning(f"Ring refresh not yet implemented for {self.id}")
        self.status = DeviceStatus.UNKNOWN


async def create_ring_camera(device_config: DeviceConfig, secrets: SecretsConfig) -> RingCamera:
    """Factory function to create a Ring camera from config."""
    return RingCamera(
        id=device_config.id,
        name=device_config.name,
        room_id=device_config.room,
        _device_id=device_config.config.get("device_id"),
    )
