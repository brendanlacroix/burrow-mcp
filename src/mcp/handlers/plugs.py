"""Plug control handlers for Burrow MCP."""

from typing import Any

from devices.manager import DeviceManager


class PlugHandlers:
    """Handlers for plug control tools."""

    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager

    async def set_plug_power(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set plug power state."""
        device_id = args["device_id"]
        on = args["on"]

        plug = self.device_manager.get_plug(device_id)
        if plug is None:
            return {"error": f"Plug not found: {device_id}"}

        await plug.set_power(on)
        return {"success": True, "device_id": device_id, "is_on": plug.is_on}
