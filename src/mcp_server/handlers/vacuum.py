"""Vacuum control handlers for Burrow MCP."""

from typing import Any

from devices.manager import DeviceManager


class VacuumHandlers:
    """Handlers for vacuum control tools."""

    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager

    async def start_vacuum(self, args: dict[str, Any]) -> dict[str, Any]:
        """Start vacuum cleaning."""
        device_id = args["device_id"]
        # room_id = args.get("room_id")  # For future room-specific cleaning

        vacuum = self.device_manager.get_vacuum(device_id)
        if vacuum is None:
            return {"error": f"Vacuum not found: {device_id}"}

        await vacuum.start()
        return {"success": True, "device_id": device_id, "vacuum_state": vacuum.vacuum_state.value}

    async def stop_vacuum(self, args: dict[str, Any]) -> dict[str, Any]:
        """Stop vacuum."""
        device_id = args["device_id"]

        vacuum = self.device_manager.get_vacuum(device_id)
        if vacuum is None:
            return {"error": f"Vacuum not found: {device_id}"}

        await vacuum.stop()
        return {"success": True, "device_id": device_id, "vacuum_state": vacuum.vacuum_state.value}

    async def dock_vacuum(self, args: dict[str, Any]) -> dict[str, Any]:
        """Send vacuum to dock."""
        device_id = args["device_id"]

        vacuum = self.device_manager.get_vacuum(device_id)
        if vacuum is None:
            return {"error": f"Vacuum not found: {device_id}"}

        await vacuum.dock()
        return {"success": True, "device_id": device_id, "vacuum_state": vacuum.vacuum_state.value}
