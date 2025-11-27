"""Scene handlers for Burrow MCP."""

import asyncio
import logging
from typing import Any

from config import BurrowConfig, SceneAction
from devices.manager import DeviceManager
from models import DeviceStatus, Light, Plug
from utils.errors import (
    DEFAULT_DEVICE_TIMEOUT,
    ErrorCategory,
    ToolError,
    classify_exception,
    get_recovery_suggestion,
)

logger = logging.getLogger(__name__)


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
        """Activate a scene with detailed status reporting."""
        scene_id = args["scene_id"]

        scene = next((s for s in self.config.scenes if s.id == scene_id), None)
        if scene is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Scene not found: {scene_id}",
                recovery="Use 'list_scenes' to see available scenes.",
            ).to_dict()

        results = []
        for action in scene.actions:
            try:
                async with asyncio.timeout(DEFAULT_DEVICE_TIMEOUT):
                    result = await self._execute_action(action)
                results.append(result)
            except asyncio.TimeoutError:
                results.append({
                    "action": action.type,
                    "success": False,
                    "error": "Action timed out",
                    "error_category": ErrorCategory.TIMEOUT.value,
                })
            except Exception as e:
                error = classify_exception(e)
                results.append({
                    "action": action.type,
                    "success": False,
                    "error": str(e),
                    "error_category": error.category.value,
                })

        # Calculate summary
        successful = sum(1 for r in results if r.get("success", False))
        failed = len(results) - successful

        # Determine overall status
        if failed == 0:
            status = "success"
        elif successful == 0:
            status = "failed"
        else:
            status = "partial"

        response: dict[str, Any] = {
            "scene_id": scene_id,
            "scene_name": scene.name,
            "status": status,
            "total_actions": len(results),
            "successful": successful,
            "failed": failed,
            "results": results,
        }

        if failed > 0:
            failed_actions = [r for r in results if not r.get("success", False)]
            response["failed_actions"] = failed_actions
            if failed == len(results):
                response["recovery"] = "All scene actions failed. Check device connectivity."
            else:
                response["recovery"] = "Some scene actions failed. Check individual devices."

        return response

    async def _execute_action(self, action: SceneAction) -> dict[str, Any]:
        """Execute a single scene action with proper error handling."""
        if action.type == "room_lights":
            return await self._execute_room_lights(action)
        elif action.type == "device":
            return await self._execute_device(action)
        elif action.type == "lock":
            return await self._execute_lock(action)
        return {
            "action": action.type,
            "success": False,
            "error": f"Unknown action type: {action.type}",
            "error_category": ErrorCategory.INVALID_INPUT.value,
        }

    async def _execute_room_lights(self, action: SceneAction) -> dict[str, Any]:
        """Execute room_lights action."""
        room_id = action.room
        if room_id == "all":
            all_results = []
            total_success = 0
            total_failed = 0
            for room in self.device_manager.get_rooms():
                result = await self._set_room_lights(
                    room.id, action.on or False, action.brightness, action.color, action.kelvin
                )
                all_results.append(result)
                if result.get("success_count", 0) > 0:
                    total_success += result.get("success_count", 0)
                if result.get("failed_count", 0) > 0:
                    total_failed += result.get("failed_count", 0)
            return {
                "action": "room_lights",
                "room": "all",
                "success": total_failed == 0,
                "total_success": total_success,
                "total_failed": total_failed,
                "results": all_results,
            }
        else:
            result = await self._set_room_lights(
                room_id, action.on or False, action.brightness, action.color, action.kelvin
            )
            result["action"] = "room_lights"
            return result

    async def _set_room_lights(
        self,
        room_id: str | None,
        on: bool,
        brightness: int | None,
        color: str | None,
        kelvin: int | None,
    ) -> dict[str, Any]:
        """Set lights in a room with proper error handling."""
        if room_id is None:
            return {
                "success": False,
                "error": "No room specified",
                "error_category": ErrorCategory.INVALID_INPUT.value,
            }

        lights = self.device_manager.get_lights(room_id)
        if not lights:
            return {
                "room_id": room_id,
                "success": True,
                "success_count": 0,
                "failed_count": 0,
                "note": "No lights in room",
            }

        results = []
        success_count = 0
        failed_count = 0

        for light in lights:
            result = {"device_id": light.id}

            # Check if light is offline
            if light.status == DeviceStatus.OFFLINE:
                result["success"] = False
                result["error"] = "Device offline"
                result["error_category"] = ErrorCategory.DEVICE_OFFLINE.value
                failed_count += 1
                results.append(result)
                continue

            try:
                async with asyncio.timeout(DEFAULT_DEVICE_TIMEOUT):
                    await light.set_power(on)
                    if on and brightness is not None:
                        await light.set_brightness(brightness)
                    if on and color is not None and light.supports_color:
                        await light.set_color(color)
                    if on and kelvin is not None:
                        await light.set_color_temp(kelvin)

                result["success"] = True
                success_count += 1
            except asyncio.TimeoutError:
                result["success"] = False
                result["error"] = "Device timeout"
                result["error_category"] = ErrorCategory.TIMEOUT.value
                failed_count += 1
            except Exception as e:
                result["success"] = False
                result["error"] = str(e)
                result["error_category"] = classify_exception(e, light.id).category.value
                failed_count += 1

            results.append(result)

        return {
            "room_id": room_id,
            "success": failed_count == 0,
            "success_count": success_count,
            "failed_count": failed_count,
            "results": results,
        }

    async def _execute_device(self, action: SceneAction) -> dict[str, Any]:
        """Execute device action with proper error handling."""
        device_id = action.device
        if device_id is None:
            return {
                "action": "device",
                "success": False,
                "error": "No device specified",
                "error_category": ErrorCategory.INVALID_INPUT.value,
            }

        device = self.device_manager.get_device(device_id)
        if device is None:
            return {
                "action": "device",
                "device": device_id,
                "success": False,
                "error": "Device not found",
                "error_category": ErrorCategory.DEVICE_NOT_FOUND.value,
            }

        # Check if device is offline
        if device.status == DeviceStatus.OFFLINE:
            return {
                "action": "device",
                "device": device_id,
                "success": False,
                "error": "Device offline",
                "error_category": ErrorCategory.DEVICE_OFFLINE.value,
            }

        try:
            async with asyncio.timeout(DEFAULT_DEVICE_TIMEOUT):
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
        except asyncio.TimeoutError:
            return {
                "action": "device",
                "device": device_id,
                "success": False,
                "error": "Device timeout",
                "error_category": ErrorCategory.TIMEOUT.value,
            }
        except Exception as e:
            return {
                "action": "device",
                "device": device_id,
                "success": False,
                "error": str(e),
                "error_category": classify_exception(e, device_id).category.value,
            }

    async def _execute_lock(self, action: SceneAction) -> dict[str, Any]:
        """Execute lock action with proper error handling."""
        device_id = action.device
        if device_id is None:
            return {
                "action": "lock",
                "success": False,
                "error": "No device specified",
                "error_category": ErrorCategory.INVALID_INPUT.value,
            }

        lock = self.device_manager.get_lock(device_id)
        if lock is None:
            return {
                "action": "lock",
                "device": device_id,
                "success": False,
                "error": "Lock not found",
                "error_category": ErrorCategory.DEVICE_NOT_FOUND.value,
            }

        # Check if lock is offline
        if lock.status == DeviceStatus.OFFLINE:
            return {
                "action": "lock",
                "device": device_id,
                "success": False,
                "error": "Lock offline",
                "error_category": ErrorCategory.DEVICE_OFFLINE.value,
            }

        try:
            async with asyncio.timeout(DEFAULT_DEVICE_TIMEOUT):
                if action.action == "lock":
                    await lock.lock()
                elif action.action == "unlock":
                    await lock.unlock()

            return {
                "action": "lock",
                "device": device_id,
                "success": True,
                "lock_state": lock.lock_state.value,
            }
        except asyncio.TimeoutError:
            return {
                "action": "lock",
                "device": device_id,
                "success": False,
                "error": "Lock timeout",
                "error_category": ErrorCategory.TIMEOUT.value,
            }
        except Exception as e:
            return {
                "action": "lock",
                "device": device_id,
                "success": False,
                "error": str(e),
                "error_category": classify_exception(e, device_id).category.value,
            }
