"""Vacuum control handlers for Burrow MCP."""

import asyncio
import logging
from typing import Any

from devices.manager import DeviceManager
from models import DeviceStatus
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


class VacuumHandlers:
    """Handlers for vacuum control tools."""

    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager

    def _check_device_online(self, device: Any, device_id: str) -> ToolError | None:
        """Check if device is online, return error if not."""
        if device.status == DeviceStatus.OFFLINE:
            return ToolError(
                category=ErrorCategory.DEVICE_OFFLINE,
                message=f"Vacuum {device_id} is offline",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_OFFLINE),
            )
        return None

    async def start_vacuum(self, args: dict[str, Any]) -> dict[str, Any]:
        """Start vacuum cleaning."""
        device_id = args["device_id"]

        vacuum = self.device_manager.get_vacuum(device_id)
        if vacuum is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Vacuum not found: {device_id}",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_NOT_FOUND),
            ).to_dict()

        if error := self._check_device_online(vacuum, device_id):
            return error.to_dict()

        try:
            await execute_with_timeout(
                vacuum.start(),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="start",
            )
            response = {
                "success": True,
                "device_id": device_id,
                "vacuum_state": vacuum.vacuum_state.value,
                "device_status": vacuum.status.value,
            }
            return await add_schedule_context(response, device_id)
        except (DeviceTimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Timeout starting vacuum {device_id}: {e}")
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Vacuum {device_id} did not respond",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.TIMEOUT),
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to start vacuum {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def stop_vacuum(self, args: dict[str, Any]) -> dict[str, Any]:
        """Stop vacuum."""
        device_id = args["device_id"]

        vacuum = self.device_manager.get_vacuum(device_id)
        if vacuum is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Vacuum not found: {device_id}",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_NOT_FOUND),
            ).to_dict()

        if error := self._check_device_online(vacuum, device_id):
            return error.to_dict()

        try:
            await execute_with_timeout(
                vacuum.stop(),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="stop",
            )
            response = {
                "success": True,
                "device_id": device_id,
                "vacuum_state": vacuum.vacuum_state.value,
                "device_status": vacuum.status.value,
            }
            return await add_schedule_context(response, device_id)
        except (DeviceTimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Timeout stopping vacuum {device_id}: {e}")
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Vacuum {device_id} did not respond",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.TIMEOUT),
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to stop vacuum {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def dock_vacuum(self, args: dict[str, Any]) -> dict[str, Any]:
        """Send vacuum to dock."""
        device_id = args["device_id"]

        vacuum = self.device_manager.get_vacuum(device_id)
        if vacuum is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Vacuum not found: {device_id}",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_NOT_FOUND),
            ).to_dict()

        if error := self._check_device_online(vacuum, device_id):
            return error.to_dict()

        try:
            await execute_with_timeout(
                vacuum.dock(),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="dock",
            )
            response = {
                "success": True,
                "device_id": device_id,
                "vacuum_state": vacuum.vacuum_state.value,
                "device_status": vacuum.status.value,
            }
            return await add_schedule_context(response, device_id)
        except (DeviceTimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Timeout docking vacuum {device_id}: {e}")
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Vacuum {device_id} did not respond",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.TIMEOUT),
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to dock vacuum {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()
