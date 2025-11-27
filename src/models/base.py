"""Base device models for Burrow MCP."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
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
