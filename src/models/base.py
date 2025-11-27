"""Base device models for Burrow MCP."""

import asyncio
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
    """Base class for all devices.

    Provides:
    - Common device attributes (id, name, type, status)
    - Operation lock for thread-safe state changes
    - Standard lifecycle methods (refresh, close, reconnect)
    """

    id: str
    name: str
    device_type: DeviceType
    room_id: str | None = None
    status: DeviceStatus = DeviceStatus.UNKNOWN
    _operation_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def __post_init__(self) -> None:
        """Initialize after dataclass __init__."""
        # Ensure lock is created (for subclasses that override __post_init__)
        if not hasattr(self, "_operation_lock") or self._operation_lock is None:
            self._operation_lock = asyncio.Lock()

    @abstractmethod
    async def refresh(self) -> None:
        """Fetch current state from device."""
        pass

    @abstractmethod
    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict for MCP responses."""
        pass

    async def close(self) -> None:
        """Close any open connections/resources.

        Subclasses should override this to clean up resources.
        """
        pass

    async def reconnect(self) -> None:
        """Attempt to reconnect to the device.

        Default implementation just refreshes state.
        Subclasses can override for more sophisticated reconnection logic.
        """
        await self.refresh()

    async def execute_operation(self, operation: Any) -> Any:
        """Execute an operation with the device lock held.

        This ensures only one operation runs at a time for this device.

        Args:
            operation: Coroutine to execute

        Returns:
            Result of the operation
        """
        async with self._operation_lock:
            return await operation
