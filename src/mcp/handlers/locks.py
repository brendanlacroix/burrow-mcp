"""Lock control handlers for Burrow MCP."""

from typing import Any

from devices.manager import DeviceManager


class LockHandlers:
    """Handlers for lock control tools."""

    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager

    async def lock_door(self, args: dict[str, Any]) -> dict[str, Any]:
        """Lock a door."""
        device_id = args["device_id"]

        lock = self.device_manager.get_lock(device_id)
        if lock is None:
            return {"error": f"Lock not found: {device_id}"}

        await lock.lock()
        return {"success": True, "device_id": device_id, "lock_state": lock.lock_state.value}

    async def unlock_door(self, args: dict[str, Any]) -> dict[str, Any]:
        """Unlock a door."""
        device_id = args["device_id"]

        lock = self.device_manager.get_lock(device_id)
        if lock is None:
            return {"error": f"Lock not found: {device_id}"}

        await lock.unlock()
        return {"success": True, "device_id": device_id, "lock_state": lock.lock_state.value}
