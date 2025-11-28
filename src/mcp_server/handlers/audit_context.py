"""Audit context utilities for device handlers.

Provides functions to log audit events for device operations,
capturing state changes for the audit log.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Module-level store reference - set by server on initialization
_store = None


def set_store(store: Any) -> None:
    """Set the store reference for audit logging.

    Called by the server during initialization to enable audit logging.
    """
    global _store
    _store = store


async def log_device_action(
    device_id: str,
    action: str,
    source: str = "mcp_tool",
    previous_state: dict[str, Any] | None = None,
    new_state: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Log a device action to the audit log.

    Args:
        device_id: ID of the device that was modified
        action: Name of the action performed (e.g., "set_power", "lock")
        source: Source of the action (default: "mcp_tool")
        previous_state: Device state before the action
        new_state: Device state after the action
        metadata: Additional metadata about the action
    """
    if not _store:
        return

    try:
        await _store.log_audit_event(
            event_type="device_action",
            device_id=device_id,
            source=source,
            action=action,
            previous_state=previous_state,
            new_state=new_state,
            metadata=metadata,
        )
        logger.debug(f"Logged audit event: {action} on {device_id}")
    except Exception as e:
        logger.warning(f"Failed to log audit event for {device_id}: {e}")


async def log_with_state_capture(
    device: Any,
    action: str,
    operation_func: Any,
    source: str = "mcp_tool",
    metadata: dict[str, Any] | None = None,
) -> Any:
    """Execute an operation and log it with state capture.

    Captures device state before and after the operation, then logs
    the audit event.

    Args:
        device: Device object with to_state_dict method
        action: Name of the action being performed
        operation_func: Async function to execute
        source: Source of the action
        metadata: Additional metadata

    Returns:
        Result of the operation function
    """
    # Capture previous state
    previous_state = None
    if hasattr(device, "to_state_dict"):
        try:
            previous_state = device.to_state_dict()
        except Exception:
            pass

    # Execute the operation
    result = await operation_func

    # Capture new state
    new_state = None
    if hasattr(device, "to_state_dict"):
        try:
            new_state = device.to_state_dict()
        except Exception:
            pass

    # Log the audit event
    await log_device_action(
        device_id=device.id,
        action=action,
        source=source,
        previous_state=previous_state,
        new_state=new_state,
        metadata=metadata,
    )

    return result
