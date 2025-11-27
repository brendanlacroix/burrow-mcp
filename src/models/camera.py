"""Camera device model."""

from dataclasses import dataclass, field
from typing import Any

from models.base import Device, DeviceType


@dataclass
class Camera(Device):
    """Base class for camera devices."""

    device_type: DeviceType = field(default=DeviceType.CAMERA, init=False)
    last_motion: str | None = None
    last_ding: str | None = None

    async def refresh(self) -> None:
        """Refresh camera state - to be implemented by subclasses."""
        pass

    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict."""
        return {
            "last_motion": self.last_motion,
            "last_ding": self.last_ding,
        }
