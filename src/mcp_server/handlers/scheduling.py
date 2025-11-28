"""Scheduling handlers for Burrow MCP.

Provides tools for creating, listing, and managing scheduled device actions.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from devices.manager import DeviceManager
from persistence import StateStore
from scheduling.scheduler import calculate_next_occurrence, humanize_time_until

logger = logging.getLogger(__name__)


class SchedulingHandlers:
    """Handlers for scheduling tools."""

    def __init__(self, device_manager: DeviceManager, store: StateStore):
        self.device_manager = device_manager
        self.store = store

    async def schedule_action(self, args: dict[str, Any]) -> dict[str, Any]:
        """Schedule an action to be executed later.

        Args:
            device_id: Target device
            action: Action to perform (turn_on, turn_off, set_brightness, etc.)
            delay_minutes: Execute after N minutes (mutually exclusive with at_time)
            at_time: Execute at specific time (ISO format or HH:MM for today)
            action_params: Parameters for the action (e.g., {"brightness": 50})
            recurrence: Recurrence pattern (optional)
            description: Human-readable description

        Returns:
            Schedule details including ID and execution time
        """
        device_id = args.get("device_id")
        action = args.get("action")
        delay_minutes = args.get("delay_minutes")
        at_time = args.get("at_time")
        action_params = args.get("action_params")
        recurrence = args.get("recurrence")
        description = args.get("description")

        # Validate device exists
        device = self.device_manager.get_device(device_id)
        if not device:
            return {"error": f"Device not found: {device_id}"}

        # Validate action
        valid_actions = [
            "turn_on", "turn_off", "set_brightness", "set_color",
            "set_temperature", "lock", "unlock",
            "start_vacuum", "stop_vacuum", "dock_vacuum",
        ]
        if action not in valid_actions:
            return {
                "error": f"Invalid action: {action}",
                "valid_actions": valid_actions,
            }

        # Determine execution time
        if delay_minutes is not None:
            execute_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
        elif at_time:
            try:
                # Try full ISO format first
                if "T" in at_time or "-" in at_time:
                    execute_at = datetime.fromisoformat(
                        at_time.replace("Z", "+00:00")
                    )
                    if execute_at.tzinfo:
                        execute_at = execute_at.replace(tzinfo=None)
                else:
                    # Assume HH:MM format for today
                    hour, minute = map(int, at_time.split(":"))
                    execute_at = datetime.utcnow().replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )
                    # If time already passed today, schedule for tomorrow
                    if execute_at <= datetime.utcnow():
                        execute_at += timedelta(days=1)
            except (ValueError, AttributeError) as e:
                return {"error": f"Invalid time format: {at_time}. Use HH:MM or ISO format."}
        else:
            return {"error": "Either delay_minutes or at_time is required"}

        # Validate recurrence pattern if provided
        if recurrence:
            rec_type = recurrence.get("type")
            if rec_type not in ["daily", "weekly", "interval"]:
                return {
                    "error": f"Invalid recurrence type: {rec_type}",
                    "valid_types": ["daily", "weekly", "interval"],
                }

        # Auto-generate description if not provided
        if not description:
            device_name = device.name or device_id
            time_str = humanize_time_until(execute_at.isoformat())
            if recurrence:
                rec_type = recurrence.get("type")
                if rec_type == "daily":
                    description = f"{action} {device_name} daily at {recurrence.get('time', 'scheduled time')}"
                elif rec_type == "weekly":
                    days = ", ".join(recurrence.get("days", []))
                    description = f"{action} {device_name} on {days}"
                else:
                    description = f"{action} {device_name} every {recurrence.get('minutes', '?')} minutes"
            else:
                description = f"{action} {device_name} {time_str}"

        # Create the scheduled action
        schedule_id = await self.store.create_scheduled_action(
            device_id=device_id,
            action=action,
            execute_at=execute_at,
            action_params=action_params,
            recurrence=recurrence,
            created_by="user:claude",
            description=description,
        )

        # Log to audit
        await self.store.log_audit_event(
            event_type="schedule_created",
            device_id=device_id,
            source="user:claude",
            action=action,
            metadata={
                "schedule_id": schedule_id,
                "execute_at": execute_at.isoformat(),
                "recurrence": recurrence,
                "action_params": action_params,
            },
        )

        return {
            "success": True,
            "schedule_id": schedule_id,
            "device_id": device_id,
            "device_name": device.name,
            "action": action,
            "execute_at": execute_at.isoformat(),
            "executes_in": humanize_time_until(execute_at.isoformat()),
            "recurrence": recurrence,
            "description": description,
        }

    async def list_scheduled_actions(self, args: dict[str, Any]) -> dict[str, Any]:
        """List scheduled actions.

        Args:
            device_id: Filter by device (optional)
            include_completed: Include completed actions (default: False)

        Returns:
            List of scheduled actions
        """
        device_id = args.get("device_id")
        include_completed = args.get("include_completed", False)

        if include_completed:
            # For now, just get pending - could add completed query later
            actions = await self.store.get_all_pending_actions(device_id)
        else:
            actions = await self.store.get_all_pending_actions(device_id)

        # Enrich with device names and time until execution
        enriched = []
        for action in actions:
            device = self.device_manager.get_device(action["device_id"])
            enriched.append({
                **action,
                "device_name": device.name if device else None,
                "executes_in": humanize_time_until(action["execute_at"]),
            })

        return {
            "scheduled_actions": enriched,
            "count": len(enriched),
        }

    async def cancel_scheduled_action(self, args: dict[str, Any]) -> dict[str, Any]:
        """Cancel a scheduled action.

        Args:
            schedule_id: ID of the schedule to cancel

        Returns:
            Success status
        """
        schedule_id = args.get("schedule_id")
        if not schedule_id:
            return {"error": "schedule_id is required"}

        # Get the action first for audit logging
        action = await self.store.get_scheduled_action(schedule_id)
        if not action:
            return {"error": f"Schedule not found: {schedule_id}"}

        if action["status"] != "pending":
            return {
                "error": f"Cannot cancel schedule with status: {action['status']}",
                "schedule_id": schedule_id,
            }

        success = await self.store.cancel_scheduled_action(schedule_id)

        if success:
            # Log to audit
            await self.store.log_audit_event(
                event_type="schedule_cancelled",
                device_id=action["device_id"],
                source="user:claude",
                action=action["action"],
                schedule_id=schedule_id,
            )

            return {
                "success": True,
                "schedule_id": schedule_id,
                "message": f"Cancelled scheduled {action['action']} on {action['device_id']}",
            }
        else:
            return {
                "error": "Failed to cancel schedule",
                "schedule_id": schedule_id,
            }

    async def modify_scheduled_action(self, args: dict[str, Any]) -> dict[str, Any]:
        """Modify a scheduled action.

        Args:
            schedule_id: ID of the schedule to modify
            delay_minutes: New delay from now (optional)
            at_time: New execution time (optional)
            recurrence: New recurrence pattern (optional, use null to remove)

        Returns:
            Updated schedule details
        """
        schedule_id = args.get("schedule_id")
        delay_minutes = args.get("delay_minutes")
        at_time = args.get("at_time")
        recurrence = args.get("recurrence")

        if not schedule_id:
            return {"error": "schedule_id is required"}

        # Get current action
        action = await self.store.get_scheduled_action(schedule_id)
        if not action:
            return {"error": f"Schedule not found: {schedule_id}"}

        if action["status"] != "pending":
            return {"error": f"Cannot modify schedule with status: {action['status']}"}

        # Determine new execution time
        new_execute_at = None
        if delay_minutes is not None:
            new_execute_at = datetime.utcnow() + timedelta(minutes=delay_minutes)
        elif at_time:
            try:
                if "T" in at_time or "-" in at_time:
                    new_execute_at = datetime.fromisoformat(
                        at_time.replace("Z", "+00:00")
                    )
                    if new_execute_at.tzinfo:
                        new_execute_at = new_execute_at.replace(tzinfo=None)
                else:
                    hour, minute = map(int, at_time.split(":"))
                    new_execute_at = datetime.utcnow().replace(
                        hour=hour, minute=minute, second=0, microsecond=0
                    )
                    if new_execute_at <= datetime.utcnow():
                        new_execute_at += timedelta(days=1)
            except (ValueError, AttributeError):
                return {"error": f"Invalid time format: {at_time}"}

        # Update the action
        success = await self.store.update_scheduled_action(
            schedule_id=schedule_id,
            execute_at=new_execute_at,
            recurrence=recurrence,
        )

        if success:
            # Get updated action
            updated = await self.store.get_scheduled_action(schedule_id)

            # Log to audit
            await self.store.log_audit_event(
                event_type="schedule_modified",
                device_id=action["device_id"],
                source="user:claude",
                action=action["action"],
                schedule_id=schedule_id,
                metadata={
                    "old_execute_at": action["execute_at"],
                    "new_execute_at": updated["execute_at"] if updated else None,
                },
            )

            device = self.device_manager.get_device(action["device_id"])
            return {
                "success": True,
                "schedule_id": schedule_id,
                "device_name": device.name if device else None,
                "action": action["action"],
                "execute_at": updated["execute_at"] if updated else None,
                "executes_in": humanize_time_until(updated["execute_at"]) if updated else None,
                "recurrence": updated.get("recurrence") if updated else None,
            }
        else:
            return {"error": "Failed to modify schedule"}

    async def get_device_history(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get audit history for a device.

        Args:
            device_id: Device to get history for
            hours: Hours of history to retrieve (default: 24)

        Returns:
            Audit history for the device
        """
        device_id = args.get("device_id")
        hours = args.get("hours", 24)

        if not device_id:
            return {"error": "device_id is required"}

        device = self.device_manager.get_device(device_id)
        if not device:
            return {"error": f"Device not found: {device_id}"}

        history = await self.store.get_device_audit_history(
            device_id=device_id,
            hours=hours,
        )

        return {
            "device_id": device_id,
            "device_name": device.name,
            "hours": hours,
            "events": history,
            "count": len(history),
        }

    async def get_audit_log(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get the system audit log.

        Args:
            hours: Hours of history to retrieve (default: 24)
            event_type: Filter by event type (optional)
            limit: Maximum entries (default: 100)

        Returns:
            Audit log entries
        """
        hours = args.get("hours", 24)
        event_type = args.get("event_type")
        limit = args.get("limit", 100)

        entries = await self.store.get_audit_log(
            hours=hours,
            event_type=event_type,
            limit=limit,
        )

        return {
            "entries": entries,
            "count": len(entries),
            "hours": hours,
            "event_type_filter": event_type,
        }


async def get_pending_schedules_for_device(
    store: StateStore,
    device_id: str,
) -> list[dict[str, Any]]:
    """Get pending schedules for a device with human-readable times.

    This is a utility function used by other handlers to check for
    pending schedules when a device is being modified.
    """
    pending = await store.get_pending_actions_for_device(device_id)

    return [
        {
            "id": p["id"],
            "action": p["action"],
            "execute_at": p["execute_at"],
            "in_minutes": _minutes_until(p["execute_at"]),
            "executes_in": humanize_time_until(p["execute_at"]),
            "description": p.get("description"),
        }
        for p in pending
    ]


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
