"""Plug device model."""

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from models.base import Device, DeviceType


@dataclass
class Plug(Device):
    """Base class for smart plug devices."""

    device_type: DeviceType = field(default=DeviceType.PLUG, init=False)
    is_on: bool = False
    power_watts: float | None = None  # if plug reports power draw

    @abstractmethod
    async def set_power(self, on: bool) -> None:
        """Turn the plug on or off."""
        pass

    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict."""
        return {
            "is_on": self.is_on,
            "power_watts": self.power_watts,
        }
