"""Base device manager for Burrow MCP."""

import asyncio
import logging
from typing import Any, TypeVar

from burrow.config import BurrowConfig, DeviceConfig, SecretsConfig
from burrow.models.device import Device, DeviceStatus, DeviceType, Light, Lock, Plug, Vacuum
from burrow.models.room import Room

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Device)


class DeviceManager:
    """Manages all devices and rooms."""

    def __init__(self, config: BurrowConfig, secrets: SecretsConfig):
        self.config = config
        self.secrets = secrets
        self._devices: dict[str, Device] = {}
        self._rooms: dict[str, Room] = {}
        self._device_factories: dict[str, Any] = {}

    def register_device_factory(self, device_type: str, factory: Any) -> None:
        """Register a factory function for creating devices of a given type.

        The factory should be a callable that takes (device_config, secrets) and returns a Device.
        """
        self._device_factories[device_type] = factory

    async def initialize(self) -> None:
        """Initialize all rooms and devices from config."""
        # Create rooms
        for room_config in self.config.rooms:
            room = Room(
                id=room_config.id,
                name=room_config.name,
                floor=room_config.floor,
            )
            self._rooms[room.id] = room
            logger.info(f"Created room: {room.name}")

        # Create devices
        for device_config in self.config.devices:
            await self._create_device(device_config)

    async def _create_device(self, device_config: DeviceConfig) -> Device | None:
        """Create a device from config."""
        factory = self._device_factories.get(device_config.type)
        if factory is None:
            logger.warning(f"No factory registered for device type: {device_config.type}")
            return None

        try:
            device = await factory(device_config, self.secrets)
            self._devices[device.id] = device

            # Add to room if specified
            if device_config.room and device_config.room in self._rooms:
                self._rooms[device_config.room].device_ids.append(device.id)

            logger.info(f"Created device: {device.name} ({device_config.type})")
            return device
        except Exception as e:
            logger.error(f"Failed to create device {device_config.id}: {e}")
            return None

    async def refresh_all(self) -> None:
        """Refresh state of all devices."""
        tasks = [device.refresh() for device in self._devices.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for device, result in zip(self._devices.values(), results):
            if isinstance(result, Exception):
                logger.error(f"Failed to refresh {device.id}: {result}")
                device.status = DeviceStatus.OFFLINE

    async def refresh_device(self, device_id: str) -> bool:
        """Refresh state of a single device."""
        device = self._devices.get(device_id)
        if device is None:
            return False
        try:
            await device.refresh()
            return True
        except Exception as e:
            logger.error(f"Failed to refresh {device_id}: {e}")
            device.status = DeviceStatus.OFFLINE
            return False

    # Device getters
    def get_device(self, device_id: str) -> Device | None:
        """Get a device by ID."""
        return self._devices.get(device_id)

    def get_devices(
        self,
        device_type: DeviceType | None = None,
        room_id: str | None = None,
        status: DeviceStatus | None = None,
    ) -> list[Device]:
        """Get devices with optional filters."""
        devices = list(self._devices.values())

        if device_type is not None:
            devices = [d for d in devices if d.device_type == device_type]

        if room_id is not None:
            devices = [d for d in devices if d.room_id == room_id]

        if status is not None:
            devices = [d for d in devices if d.status == status]

        return devices

    def get_light(self, device_id: str) -> Light | None:
        """Get a light by ID."""
        device = self._devices.get(device_id)
        return device if isinstance(device, Light) else None

    def get_lights(self, room_id: str | None = None) -> list[Light]:
        """Get all lights, optionally filtered by room."""
        devices = self.get_devices(device_type=DeviceType.LIGHT, room_id=room_id)
        return [d for d in devices if isinstance(d, Light)]

    def get_plug(self, device_id: str) -> Plug | None:
        """Get a plug by ID."""
        device = self._devices.get(device_id)
        return device if isinstance(device, Plug) else None

    def get_plugs(self, room_id: str | None = None) -> list[Plug]:
        """Get all plugs, optionally filtered by room."""
        devices = self.get_devices(device_type=DeviceType.PLUG, room_id=room_id)
        return [d for d in devices if isinstance(d, Plug)]

    def get_lock(self, device_id: str) -> Lock | None:
        """Get a lock by ID."""
        device = self._devices.get(device_id)
        return device if isinstance(device, Lock) else None

    def get_locks(self) -> list[Lock]:
        """Get all locks."""
        devices = self.get_devices(device_type=DeviceType.LOCK)
        return [d for d in devices if isinstance(d, Lock)]

    def get_vacuum(self, device_id: str) -> Vacuum | None:
        """Get a vacuum by ID."""
        device = self._devices.get(device_id)
        return device if isinstance(device, Vacuum) else None

    def get_vacuums(self) -> list[Vacuum]:
        """Get all vacuums."""
        devices = self.get_devices(device_type=DeviceType.VACUUM)
        return [d for d in devices if isinstance(d, Vacuum)]

    # Room getters
    def get_room(self, room_id: str) -> Room | None:
        """Get a room by ID."""
        return self._rooms.get(room_id)

    def get_rooms(
        self, floor: int | None = None, occupied_only: bool = False
    ) -> list[Room]:
        """Get rooms with optional filters."""
        rooms = list(self._rooms.values())

        if floor is not None:
            rooms = [r for r in rooms if r.floor == floor]

        if occupied_only:
            rooms = [r for r in rooms if r.occupied]

        return rooms

    def get_room_devices(self, room_id: str) -> list[Device]:
        """Get all devices in a room."""
        room = self._rooms.get(room_id)
        if room is None:
            return []
        return [self._devices[did] for did in room.device_ids if did in self._devices]

    def count_lights_on(self, room_id: str | None = None) -> int:
        """Count how many lights are on, optionally in a specific room."""
        lights = self.get_lights(room_id)
        return sum(1 for light in lights if light.is_on)

    # Device state as dicts for MCP responses
    def device_to_response(self, device: Device) -> dict[str, Any]:
        """Convert a device to a response dict."""
        return {
            "id": device.id,
            "name": device.name,
            "type": device.device_type.value,
            "status": device.status.value,
            "room_id": device.room_id,
            "state": device.to_state_dict(),
        }

    def room_to_response(self, room: Room) -> dict[str, Any]:
        """Convert a room to a detailed response dict."""
        devices = self.get_room_devices(room.id)
        return {
            "room": room.to_dict(),
            "devices": [self.device_to_response(d) for d in devices],
        }
