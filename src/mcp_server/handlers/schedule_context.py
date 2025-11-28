"""Schedule context utilities for device handlers.

Provides functions to check for pending schedules and add context-aware
warnings to device operation responses.
"""

import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Module-level store reference - set by server on initialization
_store = None


def set_store(store: Any) -> None:
    """Set the store reference for schedule checking.

    Called by the server during initialization to enable schedule context.
    """
    global _store
    _store = store


async def get_pending_schedules_context(device_id: str) -> list[dict[str, Any]]:
    """Get pending schedules for a device in a format suitable for responses.

    Returns a list of pending schedule summaries that can be included in
    handler responses to alert users about upcoming scheduled actions.
    """
    if not _store:
        return []

    try:
        pending = await _store.get_pending_actions_for_device(device_id)

        if not pending:
            return []

        return [
            {
                "schedule_id": p["id"],
                "action": p["action"],
                "execute_at": p["execute_at"],
                "executes_in": _humanize_time_until(p["execute_at"]),
                "in_minutes": _minutes_until(p["execute_at"]),
                "description": p.get("description"),
            }
            for p in pending
        ]
    except Exception as e:
        logger.warning(f"Error checking pending schedules for {device_id}: {e}")
        return []


async def add_schedule_context(
    response: dict[str, Any],
    device_id: str,
) -> dict[str, Any]:
    """Add pending schedule context to a handler response.

    If the device has pending scheduled actions, adds a 'pending_schedules'
    field to the response with information about upcoming actions.

    This allows Claude to inform the user about conflicting or related schedules
    when they make changes to a device.
    """
    pending = await get_pending_schedules_context(device_id)

    if pending:
        response["pending_schedules"] = pending
        # Add a hint for Claude to mention this to the user
        first_action = pending[0]
        response["schedule_hint"] = (
            f"Note: This device has a scheduled '{first_action['action']}' "
            f"{first_action['executes_in']}. You may want to ask if the user "
            "wants to cancel or modify it."
        )

    return response


def _humanize_time_until(execute_at: str) -> str:
    """Convert execute_at timestamp to human-readable time until execution."""
    try:
        exec_time = datetime.fromisoformat(execute_at.replace("Z", "+00:00"))
        now = datetime.utcnow()

        if exec_time.tzinfo:
            exec_time = exec_time.replace(tzinfo=None)

        delta = exec_time - now

        if delta.total_seconds() < 0:
            return "overdue"

        minutes = int(delta.total_seconds() / 60)
        hours = minutes // 60
        days = hours // 24

        if days > 0:
            return f"in {days} day{'s' if days != 1 else ''}"
        elif hours > 0:
            return f"in {hours} hour{'s' if hours != 1 else ''}"
        elif minutes > 0:
            return f"in {minutes} minute{'s' if minutes != 1 else ''}"
        else:
            return "in less than a minute"
    except Exception:
        return "unknown"


def _minutes_until(execute_at: str) -> int:
    """Calculate minutes until execution time."""
    try:
        exec_time = datetime.fromisoformat(execute_at.replace("Z", "+00:00"))
        if exec_time.tzinfo:
            exec_time = exec_time.replace(tzinfo=None)
        delta = exec_time - datetime.utcnow()
        return max(0, int(delta.total_seconds() / 60))
    except Exception:
        return 0
