"""Vacuum device model."""

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from models.base import Device, DeviceType


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
