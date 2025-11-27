"""August lock implementation for Burrow MCP."""

import logging
from dataclasses import dataclass, field
from typing import Any

from burrow.config import DeviceConfig, SecretsConfig
from burrow.models.device import DeviceStatus, DeviceType, Lock, LockState

logger = logging.getLogger(__name__)


@dataclass
class AugustLock(Lock):
    """August lock implementation using yalexs library."""

    device_type: DeviceType = field(default=DeviceType.LOCK, init=False)
    _lock_id: str | None = None
    _api: Any = field(default=None, repr=False)

    async def refresh(self) -> None:
        """Fetch current state from August cloud."""
        # TODO: Implement August API state refresh
        logger.warning(f"August refresh not yet implemented for {self.id}")
        self.status = DeviceStatus.UNKNOWN

    async def lock(self) -> None:
        """Lock the door."""
        # TODO: Implement August lock control
        logger.warning(f"August lock not yet implemented for {self.id}")
        raise NotImplementedError("August lock control not yet implemented")

    async def unlock(self) -> None:
        """Unlock the door."""
        # TODO: Implement August unlock control
        logger.warning(f"August unlock not yet implemented for {self.id}")
        raise NotImplementedError("August lock control not yet implemented")


async def create_august_lock(device_config: DeviceConfig, secrets: SecretsConfig) -> AugustLock:
    """Factory function to create an August lock from config.

    Args:
        device_config: Device configuration
        secrets: Secrets configuration containing August credentials

    Returns:
        Configured AugustLock instance
    """
    lock_id = secrets.august.get("lock_id") or device_config.config.get("lock_id")

    lock = AugustLock(
        id=device_config.id,
        name=device_config.name,
        room_id=device_config.room,
        _lock_id=lock_id,
    )

    return lock
