"""Lock control handlers for Burrow MCP."""

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


class LockHandlers:
    """Handlers for lock control tools."""

    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager

    def _check_device_online(self, device: Any, device_id: str) -> ToolError | None:
        """Check if device is online, return error if not."""
        if device.status == DeviceStatus.OFFLINE:
            return ToolError(
                category=ErrorCategory.DEVICE_OFFLINE,
                message=f"Lock {device_id} is offline",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_OFFLINE),
            )
        return None

    async def lock_door(self, args: dict[str, Any]) -> dict[str, Any]:
        """Lock a door."""
        device_id = args["device_id"]

        lock = self.device_manager.get_lock(device_id)
        if lock is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Lock not found: {device_id}",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_NOT_FOUND),
            ).to_dict()

        if error := self._check_device_online(lock, device_id):
            return error.to_dict()

        try:
            await execute_with_timeout(
                lock.lock(),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="lock",
            )
            response = {
                "success": True,
                "device_id": device_id,
                "lock_state": lock.lock_state.value,
                "device_status": lock.status.value,
            }
            return await add_schedule_context(response, device_id)
        except (DeviceTimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Timeout locking {device_id}: {e}")
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Lock {device_id} did not respond",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.TIMEOUT),
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to lock {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def unlock_door(self, args: dict[str, Any]) -> dict[str, Any]:
        """Unlock a door."""
        device_id = args["device_id"]

        lock = self.device_manager.get_lock(device_id)
        if lock is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Lock not found: {device_id}",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_NOT_FOUND),
            ).to_dict()

        if error := self._check_device_online(lock, device_id):
            return error.to_dict()

        try:
            await execute_with_timeout(
                lock.unlock(),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="unlock",
            )
            response = {
                "success": True,
                "device_id": device_id,
                "lock_state": lock.lock_state.value,
                "device_status": lock.status.value,
            }
            return await add_schedule_context(response, device_id)
        except (DeviceTimeoutError, asyncio.TimeoutError) as e:
            logger.error(f"Timeout unlocking {device_id}: {e}")
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Lock {device_id} did not respond",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.TIMEOUT),
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to unlock {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()
