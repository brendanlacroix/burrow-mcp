"""Device models for Burrow MCP."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DeviceType(Enum):
    """Types of supported devices."""

    LIGHT = "light"
    PLUG = "plug"
    LOCK = "lock"
    VACUUM = "vacuum"
    CAMERA = "camera"
    SENSOR = "sensor"


class DeviceStatus(Enum):
    """Device connection status."""

    ONLINE = "online"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class Device(ABC):
    """Base class for all devices."""

    id: str
    name: str
    device_type: DeviceType
    room_id: str | None = None
    status: DeviceStatus = DeviceStatus.UNKNOWN

    @abstractmethod
    async def refresh(self) -> None:
        """Fetch current state from device."""
        pass

    @abstractmethod
    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict for MCP responses."""
        pass


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


class LockState(Enum):
    """Lock states."""

    LOCKED = "locked"
    UNLOCKED = "unlocked"
    JAMMED = "jammed"
    UNKNOWN = "unknown"


@dataclass
class Lock(Device):
    """Base class for lock devices."""

    device_type: DeviceType = field(default=DeviceType.LOCK, init=False)
    lock_state: LockState = LockState.UNKNOWN
    battery_percent: int | None = None

    @abstractmethod
    async def lock(self) -> None:
        """Lock the door."""
        pass

    @abstractmethod
    async def unlock(self) -> None:
        """Unlock the door."""
        pass

    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict."""
        return {
            "lock_state": self.lock_state.value,
            "battery_percent": self.battery_percent,
        }


class VacuumState(Enum):
    """Vacuum states."""

    DOCKED = "docked"
    CLEANING = "cleaning"
    RETURNING = "returning"
    PAUSED = "paused"
    STUCK = "stuck"
    UNKNOWN = "unknown"


@dataclass
class Vacuum(Device):
    """Base class for vacuum devices."""

    device_type: DeviceType = field(default=DeviceType.VACUUM, init=False)
    vacuum_state: VacuumState = VacuumState.UNKNOWN
    battery_percent: int | None = None

    @abstractmethod
    async def start(self) -> None:
        """Start cleaning."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop cleaning."""
        pass

    @abstractmethod
    async def dock(self) -> None:
        """Return to dock."""
        pass

    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict."""
        return {
            "vacuum_state": self.vacuum_state.value,
            "battery_percent": self.battery_percent,
        }


@dataclass
class Sensor(Device):
    """Base class for sensor devices."""

    device_type: DeviceType = field(default=DeviceType.SENSOR, init=False)
    value: Any = None
    unit: str | None = None

    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict."""
        return {
            "value": self.value,
            "unit": self.unit,
        }
