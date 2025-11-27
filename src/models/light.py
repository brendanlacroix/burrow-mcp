"""Light device model."""

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from models.base import Device, DeviceType


@dataclass
class Light(Device):
    """Base class for light devices."""

    device_type: DeviceType = field(default=DeviceType.LIGHT, init=False)
    is_on: bool = False
    brightness: int = 0  # 0-100
    color: str | None = None  # hex "#FF0000" or None for white/temp
    color_temp: int | None = None  # Kelvin, e.g. 2700-6500
    supports_color: bool = True

    @abstractmethod
    async def set_power(self, on: bool) -> None:
        """Turn the light on or off."""
        pass

    @abstractmethod
    async def set_brightness(self, brightness: int) -> None:
        """Set brightness (0-100)."""
        pass

    @abstractmethod
    async def set_color(self, color: str) -> None:
        """Set color using hex code."""
        pass

    @abstractmethod
    async def set_color_temp(self, kelvin: int) -> None:
        """Set color temperature in Kelvin."""
        pass

    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict."""
        return {
            "is_on": self.is_on,
            "brightness": self.brightness,
            "color": self.color,
            "color_temp": self.color_temp,
            "supports_color": self.supports_color,
        }
