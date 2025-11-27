"""Query handlers for Burrow MCP."""

from typing import Any

from devices.manager import DeviceManager
from models import DeviceStatus, DeviceType
from presence import PresenceManager


class QueryHandlers:
    """Handlers for query tools."""

    def __init__(
        self,
        device_manager: DeviceManager,
        presence_manager: PresenceManager | None = None,
    ):
        self.device_manager = device_manager
        self.presence_manager = presence_manager

    async def list_rooms(self, args: dict[str, Any]) -> dict[str, Any]:
        """List all rooms."""
        floor = args.get("floor")
        occupied_only = args.get("occupied_only", False)

        rooms = self.device_manager.get_rooms(floor=floor, occupied_only=occupied_only)
        return {
            "rooms": [
                room.to_summary_dict(
                    lights_on=self.device_manager.count_lights_on(room.id),
                    device_count=len(room.device_ids),
                )
                for room in rooms
            ]
        }

    async def get_room_state(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get detailed room state."""
        room_id = args["room_id"]
        room = self.device_manager.get_room(room_id)
        if room is None:
            return {"error": f"Room not found: {room_id}"}

        return self.device_manager.room_to_response(room)

    async def list_devices(self, args: dict[str, Any]) -> dict[str, Any]:
        """List devices with optional filters."""
        device_type = None
        if "device_type" in args:
            try:
                device_type = DeviceType(args["device_type"])
            except ValueError:
                return {"error": f"Invalid device type: {args['device_type']}"}

        status = None
        if "status" in args:
            try:
                status = DeviceStatus(args["status"])
            except ValueError:
                return {"error": f"Invalid status: {args['status']}"}

        room_id = args.get("room_id")

        devices = self.device_manager.get_devices(
            device_type=device_type, room_id=room_id, status=status
        )
        return {"devices": [self.device_manager.device_to_response(d) for d in devices]}

    async def get_device_state(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get detailed device state."""
        device_id = args["device_id"]
        device = self.device_manager.get_device(device_id)
        if device is None:
            return {"error": f"Device not found: {device_id}"}

        await self.device_manager.refresh_device(device_id)
        return self.device_manager.device_to_response(device)

    async def get_presence(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get presence state."""
        if self.presence_manager:
            return self.presence_manager.get_presence_state().to_dict()
        return {"anyone_home": False, "occupied_rooms": [], "room_details": []}
