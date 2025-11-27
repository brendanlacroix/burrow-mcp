"""Lock device model."""

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from models.base import Device, DeviceType


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
