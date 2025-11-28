"""Light control handlers for Burrow MCP."""

import asyncio
import logging
from typing import Any

from devices.manager import DeviceManager
from models import DeviceStatus
from mcp_server.handlers.audit_context import log_device_action
from mcp_server.handlers.schedule_context import add_schedule_context
from utils.errors import (
    DEFAULT_DEVICE_TIMEOUT,
    DeviceOfflineError,
    DeviceTimeoutError,
    ErrorCategory,
    ToolError,
    classify_exception,
    execute_with_timeout,
    get_recovery_suggestion,
)

logger = logging.getLogger(__name__)


class LightHandlers:
    """Handlers for light control tools."""

    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager

    def _check_device_online(self, device: Any, device_id: str) -> ToolError | None:
        """Check if device is online, return error if not."""
        if device.status == DeviceStatus.OFFLINE:
            return ToolError(
                category=ErrorCategory.DEVICE_OFFLINE,
                message=f"Light {device_id} is offline",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_OFFLINE),
            )
        return None

    async def set_light_power(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set light power state."""
        device_id = args["device_id"]
        on = args["on"]

        light = self.device_manager.get_light(device_id)
        if light is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Light not found: {device_id}",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_NOT_FOUND),
            ).to_dict()

        # Check if device is online
        if error := self._check_device_online(light, device_id):
            return error.to_dict()

        try:
            # Capture state before operation
            previous_state = light.to_state_dict()

            await execute_with_timeout(
                light.set_power(on),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="set_power",
            )

            # Log audit event
            await log_device_action(
                device_id=device_id,
                action="set_power",
                previous_state=previous_state,
                new_state=light.to_state_dict(),
                metadata={"on": on},
            )

            response = {
                "success": True,
                "device_id": device_id,
                "is_on": light.is_on,
                "device_status": light.status.value,
            }
            return await add_schedule_context(response, device_id)
        except (DeviceTimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Timeout setting power for {device_id}: {e}")
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Light {device_id} did not respond",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.TIMEOUT),
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to set power for {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def set_light_brightness(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set light brightness."""
        device_id = args["device_id"]
        brightness = args["brightness"]

        light = self.device_manager.get_light(device_id)
        if light is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Light not found: {device_id}",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_NOT_FOUND),
            ).to_dict()

        if error := self._check_device_online(light, device_id):
            return error.to_dict()

        # Validate brightness range
        if not 0 <= brightness <= 100:
            return ToolError(
                category=ErrorCategory.INVALID_INPUT,
                message="Brightness must be between 0 and 100",
                device_id=device_id,
                recovery="Provide a brightness value from 0 to 100.",
            ).to_dict()

        try:
            previous_state = light.to_state_dict()

            await execute_with_timeout(
                light.set_brightness(brightness),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="set_brightness",
            )

            await log_device_action(
                device_id=device_id,
                action="set_brightness",
                previous_state=previous_state,
                new_state=light.to_state_dict(),
                metadata={"brightness": brightness},
            )

            response = {
                "success": True,
                "device_id": device_id,
                "brightness": light.brightness,
                "device_status": light.status.value,
            }
            return await add_schedule_context(response, device_id)
        except (DeviceTimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Timeout setting brightness for {device_id}: {e}")
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Light {device_id} did not respond",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.TIMEOUT),
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to set brightness for {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def set_light_color(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set light color."""
        device_id = args["device_id"]
        color = args["color"]

        light = self.device_manager.get_light(device_id)
        if light is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Light not found: {device_id}",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_NOT_FOUND),
            ).to_dict()

        if error := self._check_device_online(light, device_id):
            return error.to_dict()

        if not light.supports_color:
            return ToolError(
                category=ErrorCategory.INVALID_INPUT,
                message=f"Light {device_id} does not support color",
                device_id=device_id,
                recovery="This light only supports brightness and color temperature.",
            ).to_dict()

        try:
            previous_state = light.to_state_dict()

            await execute_with_timeout(
                light.set_color(color),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="set_color",
            )

            await log_device_action(
                device_id=device_id,
                action="set_color",
                previous_state=previous_state,
                new_state=light.to_state_dict(),
                metadata={"color": color},
            )

            response = {
                "success": True,
                "device_id": device_id,
                "color": light.color,
                "device_status": light.status.value,
            }
            return await add_schedule_context(response, device_id)
        except (DeviceTimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Timeout setting color for {device_id}: {e}")
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Light {device_id} did not respond",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.TIMEOUT),
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to set color for {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def set_light_temperature(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set light color temperature."""
        device_id = args["device_id"]
        kelvin = args["kelvin"]

        light = self.device_manager.get_light(device_id)
        if light is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Light not found: {device_id}",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_NOT_FOUND),
            ).to_dict()

        if error := self._check_device_online(light, device_id):
            return error.to_dict()

        # Validate kelvin range
        if not 1500 <= kelvin <= 9000:
            return ToolError(
                category=ErrorCategory.INVALID_INPUT,
                message="Color temperature must be between 1500K and 9000K",
                device_id=device_id,
                recovery="Provide a kelvin value from 1500 (warm) to 9000 (cool).",
            ).to_dict()

        try:
            previous_state = light.to_state_dict()

            await execute_with_timeout(
                light.set_color_temp(kelvin),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="set_color_temp",
            )

            await log_device_action(
                device_id=device_id,
                action="set_color_temp",
                previous_state=previous_state,
                new_state=light.to_state_dict(),
                metadata={"kelvin": kelvin},
            )

            response = {
                "success": True,
                "device_id": device_id,
                "color_temp": light.color_temp,
                "device_status": light.status.value,
            }
            return await add_schedule_context(response, device_id)
        except (DeviceTimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Timeout setting color temp for {device_id}: {e}")
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Light {device_id} did not respond",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.TIMEOUT),
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to set color temp for {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def set_room_lights(self, args: dict[str, Any]) -> dict[str, Any]:
        """Control all lights in a room with detailed status reporting."""
        room_id = args["room_id"]
        on = args["on"]
        brightness = args.get("brightness")
        color = args.get("color")
        kelvin = args.get("kelvin")

        room = self.device_manager.get_room(room_id)
        if room is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Room not found: {room_id}",
                recovery="Use 'list_rooms' to see available rooms.",
            ).to_dict()

        lights = self.device_manager.get_lights(room_id)
        if not lights:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"No lights found in room: {room_id}",
                recovery="This room has no light devices configured.",
            ).to_dict()

        results = []
        for light in lights:
            result = {"device_id": light.id, "device_name": light.name}

            # Check if light is offline before attempting operations
            if light.status == DeviceStatus.OFFLINE:
                result["success"] = False
                result["error"] = "Device offline"
                result["error_category"] = ErrorCategory.DEVICE_OFFLINE.value
                results.append(result)
                continue

            try:
                # Use timeout for each device operation
                async with asyncio.timeout(DEFAULT_DEVICE_TIMEOUT):
                    await light.set_power(on)
                    if on and brightness is not None:
                        await light.set_brightness(brightness)
                    if on and color is not None and light.supports_color:
                        await light.set_color(color)
                    if on and kelvin is not None:
                        await light.set_color_temp(kelvin)

                result["success"] = True
                result["is_on"] = light.is_on
                if brightness is not None:
                    result["brightness"] = light.brightness

            except asyncio.TimeoutError:
                result["success"] = False
                result["error"] = "Device timeout"
                result["error_category"] = ErrorCategory.TIMEOUT.value
            except Exception as e:
                result["success"] = False
                result["error"] = str(e)
                result["error_category"] = classify_exception(e, light.id).category.value

            results.append(result)

        # Calculate summary
        successful = sum(1 for r in results if r.get("success"))
        failed = len(results) - successful

        # Determine overall status
        if failed == 0:
            status = "success"
        elif successful == 0:
            status = "failed"
        else:
            status = "partial"

        response: dict[str, Any] = {
            "room_id": room_id,
            "room_name": room.name,
            "status": status,
            "total": len(results),
            "successful": successful,
            "failed": failed,
            "results": results,
        }

        # Add recovery info if there were failures
        if failed > 0:
            failed_devices = [r["device_id"] for r in results if not r.get("success")]
            response["failed_devices"] = failed_devices
            if failed == len(results):
                response["recovery"] = (
                    "All lights failed. Check room power and device connections."
                )
            else:
                response["recovery"] = (
                    f"Some lights failed: {', '.join(failed_devices)}. "
                    "Check these devices individually."
                )

        return response
