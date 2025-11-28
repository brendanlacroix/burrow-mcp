"""Device manager for Burrow MCP."""

import asyncio
import logging
from pathlib import Path
from typing import Any

from config import BurrowConfig, DeviceConfig, SecretsConfig
from models import Device, DeviceStatus, DeviceType, Light, Lock, Plug, Vacuum
from models.room import Room
from persistence import StateStore, get_store
from utils.health import DeviceHealth, HealthMonitor

logger = logging.getLogger(__name__)


class DeviceManager:
    """Manages all devices and rooms."""

    def __init__(
        self,
        config: BurrowConfig,
        secrets: SecretsConfig,
        db_path: Path | str | None = None,
        health_check_interval: float = 60.0,
    ):
        self.config = config
        self.secrets = secrets
        self._devices: dict[str, Device] = {}
        self._rooms: dict[str, Room] = {}
        self._device_factories: dict[str, Any] = {}
        self._db_path = db_path
        self._store: StateStore | None = None

        # Initialize health monitor
        self._health_monitor = HealthMonitor(
            check_interval=health_check_interval,
            unhealthy_threshold=3,
            reconnect_delay=30.0,
        )
        self._health_monitor_started = False

    @property
    def health_monitor(self) -> HealthMonitor:
        """Get the health monitor instance."""
        return self._health_monitor

    def register_device_factory(self, device_type: str, factory: Any) -> None:
        """Register a factory function for creating devices of a given type.

        The factory should be a callable that takes (device_config, secrets) and returns a Device.
        """
        self._device_factories[device_type] = factory

    async def initialize(self) -> None:
        """Initialize all rooms and devices from config."""
        # Initialize state store
        self._store = await get_store(self._db_path)

        # Load persisted room states
        room_states = await self._store.load_all_room_states()

        # Create rooms
        for room_config in self.config.rooms:
            room = Room(
                id=room_config.id,
                name=room_config.name,
                floor=room_config.floor,
            )
            # Restore persisted occupancy
            if room.id in room_states:
                room.occupied = room_states[room.id]

            self._rooms[room.id] = room
            logger.info(f"Created room: {room.name}")

        # Create devices
        for device_config in self.config.devices:
            await self._create_device(device_config)

        # Start health monitoring after all devices are created
        await self.start_health_monitoring()

    async def start_health_monitoring(self) -> None:
        """Start the health monitoring background task."""
        if self._health_monitor_started:
            return

        # Register all devices with the health monitor
        for device_id, device in self._devices.items():
            self._health_monitor.register_device(
                device_id=device_id,
                check_func=device.refresh,
                reconnect_func=getattr(device, "reconnect", None),
            )
            logger.debug(f"Registered device {device_id} with health monitor")

        await self._health_monitor.start()
        self._health_monitor_started = True
        logger.info(
            f"Health monitoring started for {len(self._devices)} devices "
            f"(check interval: {self._health_monitor.check_interval}s)"
        )

    async def stop_health_monitoring(self) -> None:
        """Stop the health monitoring background task."""
        if self._health_monitor_started:
            await self._health_monitor.stop()
            self._health_monitor_started = False
            logger.info("Health monitoring stopped")

    async def shutdown(self) -> None:
        """Gracefully shutdown, persisting state and closing resources."""
        # Stop health monitoring
        await self.stop_health_monitoring()

        # Close device connections
        for device in self._devices.values():
            if hasattr(device, "close"):
                try:
                    await device.close()
                    logger.debug(f"Closed device connection: {device.id}")
                except Exception as e:
                    logger.warning(f"Error closing device {device.id}: {e}")

        # Save all device states
        if self._store:
            for device in self._devices.values():
                await self._store.save_device_state(
                    device.id,
                    device.device_type.value,
                    device.to_state_dict(),
                )

            # Save room states
            for room in self._rooms.values():
                await self._store.save_room_state(room.id, room.occupied)

            logger.info("Persisted device and room states")

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

    async def refresh_all(self, timeout: float = 30.0) -> None:
        """Refresh state of all devices with timeout protection.

        Args:
            timeout: Maximum time to wait for all refreshes (default 30s)
        """
        tasks = [device.refresh() for device in self._devices.values()]
        try:
            async with asyncio.timeout(timeout):
                results = await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.TimeoutError:
            logger.error(f"refresh_all timed out after {timeout}s")
            # Mark all devices as potentially offline on timeout
            for device in self._devices.values():
                device.status = DeviceStatus.OFFLINE
            return
        for device, result in zip(self._devices.values(), results):
            if isinstance(result, Exception):
                logger.error(f"Failed to refresh {device.id}: {result}")
                device.status = DeviceStatus.OFFLINE
                # Record failure in health monitor
                health = self._health_monitor.get_device_health(device.id)
                if health:
                    health.record_failure()
            else:
                # Persist updated state
                await self._persist_device_state(device)
                # Record success in health monitor
                health = self._health_monitor.get_device_health(device.id)
                if health:
                    health.record_success()

    async def refresh_device(self, device_id: str) -> bool:
        """Refresh state of a single device."""
        device = self._devices.get(device_id)
        if device is None:
            return False
        try:
            await device.refresh()
            await self._persist_device_state(device)
            # Record success in health monitor
            health = self._health_monitor.get_device_health(device_id)
            if health:
                health.record_success()
            return True
        except Exception as e:
            logger.error(f"Failed to refresh {device_id}: {e}")
            device.status = DeviceStatus.OFFLINE
            # Record failure in health monitor
            health = self._health_monitor.get_device_health(device_id)
            if health:
                health.record_failure()
            return False

    async def _persist_device_state(self, device: Device) -> None:
        """Persist a device's current state."""
        if self._store:
            await self._store.save_device_state(
                device.id,
                device.device_type.value,
                device.to_state_dict(),
            )

    async def record_device_event(
        self,
        device_id: str,
        event_type: str,
        state: dict[str, Any] | None = None,
    ) -> None:
        """Record a device event in history."""
        if self._store:
            await self._store.record_device_event(device_id, event_type, state)

    async def update_room_presence(
        self,
        room_id: str,
        occupied: bool,
        confidence: float | None = None,
    ) -> None:
        """Update room presence and persist."""
        room = self._rooms.get(room_id)
        if room:
            room.occupied = occupied
            if self._store:
                await self._store.save_room_state(room_id, occupied)
                await self._store.record_presence_event(room_id, occupied, confidence)

    # Health monitoring getters
    def get_device_health(self, device_id: str) -> DeviceHealth | None:
        """Get health status for a specific device."""
        return self._health_monitor.get_device_health(device_id)

    def get_all_health(self) -> dict[str, DeviceHealth]:
        """Get health status for all devices."""
        return self._health_monitor.get_all_health()

    def get_unhealthy_devices(self) -> list[str]:
        """Get list of unhealthy device IDs."""
        return self._health_monitor.get_unhealthy_devices()

    def get_health_summary(self) -> dict[str, Any]:
        """Get a summary of all device health."""
        return self._health_monitor.get_summary()

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
        """Convert a device to a response dict with health info."""
        response = {
            "id": device.id,
            "name": device.name,
            "type": device.device_type.value,
            "status": device.status.value,
            "room_id": device.room_id,
            "state": device.to_state_dict(),
        }

        # Add health info if available
        health = self._health_monitor.get_device_health(device.id)
        if health:
            response["health"] = {
                "is_healthy": health.is_healthy,
                "consecutive_failures": health.consecutive_failures,
                "failure_rate": round(health.failure_rate, 3),
            }
            if health.last_successful_contact:
                response["health"]["last_success"] = health.last_successful_contact.isoformat()

        return response

    def room_to_response(self, room: Room) -> dict[str, Any]:
        """Convert a room to a detailed response dict."""
        devices = self.get_room_devices(room.id)
        return {
            "room": room.to_dict(),
            "devices": [self.device_to_response(d) for d in devices],
        }
