"""Scene handlers for Burrow MCP."""

from typing import Any

from config import BurrowConfig, SceneAction
from devices.manager import DeviceManager
from models import Light, Plug


class SceneHandlers:
    """Handlers for scene tools."""

    def __init__(self, config: BurrowConfig, device_manager: DeviceManager):
        self.config = config
        self.device_manager = device_manager

    async def list_scenes(self, args: dict[str, Any]) -> dict[str, Any]:
        """List available scenes."""
        return {
            "scenes": [
                {"id": scene.id, "name": scene.name, "action_count": len(scene.actions)}
                for scene in self.config.scenes
            ]
        }

    async def activate_scene(self, args: dict[str, Any]) -> dict[str, Any]:
        """Activate a scene."""
        scene_id = args["scene_id"]

        scene = next((s for s in self.config.scenes if s.id == scene_id), None)
        if scene is None:
            return {"error": f"Scene not found: {scene_id}"}

        results = []
        for action in scene.actions:
            try:
                result = await self._execute_action(action)
                results.append(result)
            except Exception as e:
                results.append({"action": action.type, "success": False, "error": str(e)})

        return {"scene_id": scene_id, "scene_name": scene.name, "results": results}

    async def _execute_action(self, action: SceneAction) -> dict[str, Any]:
        """Execute a single scene action."""
        if action.type == "room_lights":
            return await self._execute_room_lights(action)
        elif action.type == "device":
            return await self._execute_device(action)
        elif action.type == "lock":
            return await self._execute_lock(action)
        return {"action": action.type, "error": "Unknown action type"}

    async def _execute_room_lights(self, action: SceneAction) -> dict[str, Any]:
        """Execute room_lights action."""
        room_id = action.room
        if room_id == "all":
            all_results = []
            for room in self.device_manager.get_rooms():
                result = await self._set_room_lights(
                    room.id, action.on or False, action.brightness, action.color, action.kelvin
                )
                all_results.append(result)
            return {"action": "room_lights", "room": "all", "results": all_results}
        else:
            return await self._set_room_lights(
                room_id, action.on or False, action.brightness, action.color, action.kelvin
            )

    async def _set_room_lights(
        self,
        room_id: str | None,
        on: bool,
        brightness: int | None,
        color: str | None,
        kelvin: int | None,
    ) -> dict[str, Any]:
        """Set lights in a room."""
        if room_id is None:
            return {"action": "room_lights", "error": "No room specified"}

        lights = self.device_manager.get_lights(room_id)
        results = []
        for light in lights:
            try:
                await light.set_power(on)
                if on and brightness is not None:
                    await light.set_brightness(brightness)
                if on and color is not None and light.supports_color:
                    await light.set_color(color)
                if on and kelvin is not None:
                    await light.set_color_temp(kelvin)
                results.append({"device_id": light.id, "success": True})
            except Exception as e:
                results.append({"device_id": light.id, "success": False, "error": str(e)})

        return {"action": "room_lights", "room_id": room_id, "results": results}

    async def _execute_device(self, action: SceneAction) -> dict[str, Any]:
        """Execute device action."""
        device_id = action.device
        if device_id is None:
            return {"action": "device", "error": "No device specified"}

        device = self.device_manager.get_device(device_id)
        if device is None:
            return {"action": "device", "device": device_id, "error": "Device not found"}

        if isinstance(device, Light):
            if action.on is not None:
                await device.set_power(action.on)
            if action.brightness is not None:
                await device.set_brightness(action.brightness)
            if action.color is not None and device.supports_color:
                await device.set_color(action.color)
            if action.kelvin is not None:
                await device.set_color_temp(action.kelvin)
        elif isinstance(device, Plug):
            if action.on is not None:
                await device.set_power(action.on)

        return {"action": "device", "device": device_id, "success": True}

    async def _execute_lock(self, action: SceneAction) -> dict[str, Any]:
        """Execute lock action."""
        device_id = action.device
        if device_id is None:
            return {"action": "lock", "error": "No device specified"}

        lock = self.device_manager.get_lock(device_id)
        if lock is None:
            return {"action": "lock", "device": device_id, "error": "Lock not found"}

        if action.action == "lock":
            await lock.lock()
        elif action.action == "unlock":
            await lock.unlock()

        return {"action": "lock", "device": device_id, "lock_state": lock.lock_state.value}
