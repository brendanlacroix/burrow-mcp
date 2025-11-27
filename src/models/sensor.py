"""Sensor device model."""

from dataclasses import dataclass, field
from typing import Any

from models.base import Device, DeviceType


@dataclass
class Sensor(Device):
    """Base class for sensor devices."""

    device_type: DeviceType = field(default=DeviceType.SENSOR, init=False)
    value: Any = None
    unit: str | None = None

    async def refresh(self) -> None:
        """Sensors typically push data, so refresh is a no-op."""
        pass

    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict."""
        return {
            "value": self.value,
            "unit": self.unit,
        }
