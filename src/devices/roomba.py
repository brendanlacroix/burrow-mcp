"""Roomba vacuum implementation for Burrow MCP."""

import logging
from dataclasses import dataclass, field
from typing import Any

from config import DeviceConfig, SecretsConfig
from models.base import DeviceStatus, DeviceType
from models.vacuum import Vacuum

logger = logging.getLogger(__name__)


@dataclass
class RoombaVacuum(Vacuum):
    """Roomba vacuum implementation using roombapy library."""

    device_type: DeviceType = field(default=DeviceType.VACUUM, init=False)
    _ip: str | None = None
    _blid: str | None = None
    _password: str | None = None
    _robot: Any = field(default=None, repr=False)

    async def refresh(self) -> None:
        """Fetch current state from Roomba."""
        # TODO: Implement Roomba state refresh
        logger.warning(f"Roomba refresh not yet implemented for {self.id}")
        self.status = DeviceStatus.UNKNOWN

    async def start(self) -> None:
        """Start cleaning."""
        logger.warning(f"Roomba start not yet implemented for {self.id}")
        raise NotImplementedError("Roomba control not yet implemented")

    async def stop(self) -> None:
        """Stop cleaning."""
        logger.warning(f"Roomba stop not yet implemented for {self.id}")
        raise NotImplementedError("Roomba control not yet implemented")

    async def dock(self) -> None:
        """Return to dock."""
        logger.warning(f"Roomba dock not yet implemented for {self.id}")
        raise NotImplementedError("Roomba control not yet implemented")


async def create_roomba_vacuum(
    device_config: DeviceConfig, secrets: SecretsConfig
) -> RoombaVacuum:
    """Factory function to create a Roomba vacuum from config."""
    ip = device_config.config.get("ip")
    blid = secrets.roomba.get("blid") or device_config.config.get("blid")
    password = secrets.roomba.get("password") or device_config.config.get("password")

    return RoombaVacuum(
        id=device_config.id,
        name=device_config.name,
        room_id=device_config.room,
        _ip=ip,
        _blid=blid,
        _password=password,
    )
