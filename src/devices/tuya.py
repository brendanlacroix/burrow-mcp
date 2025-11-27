"""Tuya smart plug implementation for Burrow MCP."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from config import DeviceConfig, SecretsConfig, get_device_secret
from models.base import DeviceStatus, DeviceType
from models.plug import Plug

logger = logging.getLogger(__name__)


@dataclass
class TuyaPlug(Plug):
    """Tuya smart plug implementation."""

    device_type: DeviceType = field(default=DeviceType.PLUG, init=False)
    _tuya_device: Any = field(default=None, repr=False)
    _device_id: str | None = None
    _local_key: str | None = None
    _ip: str | None = None

    async def _run_sync(self, func: Any, *args: Any) -> Any:
        """Run a synchronous Tuya function in a thread."""
        return await asyncio.to_thread(func, *args)

    async def refresh(self) -> None:
        """Fetch current state from the Tuya plug."""
        if self._tuya_device is None:
            self.status = DeviceStatus.OFFLINE
            return

        try:
            status = await self._run_sync(self._tuya_device.status)
            if status and "dps" in status:
                self.is_on = status["dps"].get("1", False)
                power = status["dps"].get("19")
                if power is not None:
                    self.power_watts = float(power) / 10.0
            self.status = DeviceStatus.ONLINE
        except Exception as e:
            logger.error(f"Failed to refresh Tuya plug {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE

    async def set_power(self, on: bool) -> None:
        """Turn the plug on or off."""
        if self._tuya_device is None:
            raise RuntimeError(f"Tuya plug {self.id} not connected")

        try:
            if on:
                await self._run_sync(self._tuya_device.turn_on)
            else:
                await self._run_sync(self._tuya_device.turn_off)
            self.is_on = on
            self.status = DeviceStatus.ONLINE
        except Exception as e:
            logger.error(f"Failed to set power for Tuya plug {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE
            raise


async def create_tuya_plug(device_config: DeviceConfig, secrets: SecretsConfig) -> TuyaPlug:
    """Factory function to create a Tuya plug from config."""
    try:
        import tinytuya
    except ImportError:
        logger.error("tinytuya package not installed. Install with: pip install tinytuya")
        raise

    device_id = device_config.config.get("device_id")
    ip = device_config.config.get("ip")

    local_key = get_device_secret(secrets, "tuya", device_config.id, "local_key")
    if not local_key:
        local_key = device_config.config.get("local_key")

    if not device_id or not local_key:
        raise ValueError(f"Tuya plug {device_config.id} requires device_id and local_key")

    plug = TuyaPlug(
        id=device_config.id,
        name=device_config.name,
        room_id=device_config.room,
        _device_id=device_id,
        _local_key=local_key,
        _ip=ip,
    )

    if ip:
        plug._tuya_device = tinytuya.OutletDevice(device_id, ip, local_key)
    else:
        plug._tuya_device = tinytuya.OutletDevice(device_id, "Auto", local_key)

    plug._tuya_device.set_version(3.3)

    await plug.refresh()

    return plug
