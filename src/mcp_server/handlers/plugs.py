"""Plug control handlers for Burrow MCP."""

import asyncio
import logging
from typing import Any

from devices.manager import DeviceManager
from models import DeviceStatus
from mcp_server.handlers.audit_context import log_device_action
from mcp_server.handlers.schedule_context import add_schedule_context
from utils.errors import (
    DEFAULT_DEVICE_TIMEOUT,
    DeviceTimeoutError,
    ErrorCategory,
    ToolError,
    classify_exception,
    execute_with_timeout,
    get_recovery_suggestion,
)

logger = logging.getLogger(__name__)


class PlugHandlers:
    """Handlers for plug control tools."""

    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager

    def _check_device_online(self, device: Any, device_id: str) -> ToolError | None:
        """Check if device is online, return error if not."""
        if device.status == DeviceStatus.OFFLINE:
            return ToolError(
                category=ErrorCategory.DEVICE_OFFLINE,
                message=f"Plug {device_id} is offline",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_OFFLINE),
            )
        return None

    async def set_plug_power(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set plug power state."""
        device_id = args["device_id"]
        on = args["on"]

        plug = self.device_manager.get_plug(device_id)
        if plug is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Plug not found: {device_id}",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_NOT_FOUND),
            ).to_dict()

        if error := self._check_device_online(plug, device_id):
            return error.to_dict()

        try:
            previous_state = plug.to_state_dict()

            await execute_with_timeout(
                plug.set_power(on),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="set_power",
            )

            await log_device_action(
                device_id=device_id,
                action="set_power",
                previous_state=previous_state,
                new_state=plug.to_state_dict(),
                metadata={"on": on},
            )

            response = {
                "success": True,
                "device_id": device_id,
                "is_on": plug.is_on,
                "device_status": plug.status.value,
            }
            return await add_schedule_context(response, device_id)
        except (DeviceTimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Timeout setting power for plug {device_id}: {e}")
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Plug {device_id} did not respond",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.TIMEOUT),
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to set power for plug {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()
