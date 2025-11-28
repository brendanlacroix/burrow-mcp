"""Scheduler service for executing timed actions.

Provides a background service that monitors scheduled actions and executes
them when due. Supports both one-time and recurring schedules.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Callable

from devices.manager import DeviceManager
from persistence import StateStore

logger = logging.getLogger(__name__)


def calculate_next_occurrence(
    recurrence: dict[str, Any],
    from_time: datetime | None = None,
) -> datetime | None:
    """Calculate the next occurrence based on recurrence pattern.

    Recurrence patterns:
    - {"type": "daily", "time": "07:00"}
    - {"type": "weekly", "days": ["mon", "tue"], "time": "18:00"}
    - {"type": "interval", "minutes": 30}
    - {"type": "interval", "minutes": 30, "until": "2024-01-15T22:00:00"}

    Args:
        recurrence: Recurrence pattern dict
        from_time: Calculate next occurrence after this time (default: now)

    Returns:
        Next occurrence datetime, or None if schedule has ended
    """
    if not recurrence:
        return None

    now = from_time or datetime.utcnow()
    rec_type = recurrence.get("type")

    if rec_type == "interval":
        minutes = recurrence.get("minutes", 60)
        next_time = now + timedelta(minutes=minutes)

        # Check if there's an end time
        until = recurrence.get("until")
        if until:
            end_time = datetime.fromisoformat(until.replace("Z", "+00:00"))
            if next_time > end_time:
                return None

        return next_time

    elif rec_type == "daily":
        time_str = recurrence.get("time", "00:00")
        hour, minute = map(int, time_str.split(":"))

        # Next occurrence is today at specified time, or tomorrow if already passed
        next_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if next_time <= now:
            next_time += timedelta(days=1)

        return next_time

    elif rec_type == "weekly":
        days = recurrence.get("days", [])
        time_str = recurrence.get("time", "00:00")
        hour, minute = map(int, time_str.split(":"))

        # Map day names to weekday numbers (0=Monday)
        day_map = {
            "mon": 0, "monday": 0,
            "tue": 1, "tuesday": 1,
            "wed": 2, "wednesday": 2,
            "thu": 3, "thursday": 3,
            "fri": 4, "friday": 4,
            "sat": 5, "saturday": 5,
            "sun": 6, "sunday": 6,
        }

        target_days = [day_map.get(d.lower(), -1) for d in days if d.lower() in day_map]
        if not target_days:
            return None

        # Find the next matching day
        for days_ahead in range(8):  # Check up to a week ahead
            check_date = now + timedelta(days=days_ahead)
            if check_date.weekday() in target_days:
                next_time = check_date.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                if next_time > now:
                    return next_time

        return None

    return None


class Scheduler:
    """Background scheduler for executing timed actions.

    The scheduler runs a loop that:
    1. Checks for due actions every N seconds
    2. Executes due actions
    3. Updates recurring actions with next execution time
    4. Logs all executions to audit log
    """

    def __init__(
        self,
        store: StateStore,
        device_manager: DeviceManager,
        check_interval: float = 10.0,
    ):
        """Initialize scheduler.

        Args:
            store: State store for persistence
            device_manager: Device manager for executing actions
            check_interval: Seconds between checking for due actions
        """
        self.store = store
        self.device_manager = device_manager
        self.check_interval = check_interval

        self._running = False
        self._task: asyncio.Task | None = None

        # Action handlers map action names to execution functions
        self._action_handlers: dict[str, Callable] = {
            "turn_on": self._execute_turn_on,
            "turn_off": self._execute_turn_off,
            "set_brightness": self._execute_set_brightness,
            "set_color": self._execute_set_color,
            "set_temperature": self._execute_set_temperature,
            "lock": self._execute_lock,
            "unlock": self._execute_unlock,
            "start_vacuum": self._execute_start_vacuum,
            "stop_vacuum": self._execute_stop_vacuum,
            "dock_vacuum": self._execute_dock_vacuum,
        }

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduler started")

    async def stop(self) -> None:
        """Stop the scheduler loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Scheduler stopped")

    async def _scheduler_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            try:
                await self._process_due_actions()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(self.check_interval)

    async def _process_due_actions(self) -> None:
        """Process all actions that are due."""
        due_actions = await self.store.get_due_actions()

        for action in due_actions:
            try:
                await self._execute_action(action)
            except Exception as e:
                logger.error(
                    f"Failed to execute scheduled action {action['id']}: {e}"
                )
                await self.store.mark_action_failed(action["id"], str(e))

                # Log failure to audit
                await self.store.log_audit_event(
                    event_type="schedule_failed",
                    device_id=action["device_id"],
                    source=f"schedule:{action['id']}",
                    action=action["action"],
                    metadata={"error": str(e), "schedule_id": action["id"]},
                )

    async def _execute_action(self, action: dict[str, Any]) -> None:
        """Execute a single scheduled action."""
        device_id = action["device_id"]
        action_name = action["action"]
        action_params = action.get("action_params", {})
        schedule_id = action["id"]

        logger.info(
            f"Executing scheduled action {schedule_id}: "
            f"{action_name} on {device_id}"
        )

        # Get device for state capture
        device = self.device_manager.get_device(device_id)
        previous_state = device.to_state_dict() if device else None

        # Find and execute the action handler
        handler = self._action_handlers.get(action_name)
        if not handler:
            raise ValueError(f"Unknown action: {action_name}")

        await handler(device_id, action_params)

        # Refresh device and capture new state
        if device:
            await device.refresh()
            new_state = device.to_state_dict()
        else:
            new_state = None

        # Log execution to audit
        await self.store.log_audit_event(
            event_type="schedule_executed",
            device_id=device_id,
            source=f"schedule:{schedule_id}",
            action=action_name,
            previous_state=previous_state,
            new_state=new_state,
            schedule_id=schedule_id,
            metadata={"action_params": action_params},
        )

        # Handle recurrence or mark completed
        recurrence = action.get("recurrence")
        if recurrence:
            next_time = calculate_next_occurrence(recurrence)
            if next_time:
                await self.store.mark_action_executed(schedule_id, next_time)
                logger.info(
                    f"Rescheduled {schedule_id} for {next_time.isoformat()}"
                )
            else:
                # Recurrence has ended
                await self.store.mark_action_executed(schedule_id, None)
                logger.info(f"Recurring schedule {schedule_id} has ended")
        else:
            await self.store.mark_action_executed(schedule_id, None)
            logger.info(f"Completed one-time schedule {schedule_id}")

    # Action handlers
    async def _execute_turn_on(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Turn on a device."""
        device = self.device_manager.get_device(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")

        if hasattr(device, "set_power"):
            await device.set_power(True)
        else:
            raise ValueError(f"Device {device_id} does not support power control")

    async def _execute_turn_off(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Turn off a device."""
        device = self.device_manager.get_device(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")

        if hasattr(device, "set_power"):
            await device.set_power(False)
        else:
            raise ValueError(f"Device {device_id} does not support power control")

    async def _execute_set_brightness(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Set device brightness."""
        device = self.device_manager.get_device(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")

        brightness = params.get("brightness")
        if brightness is None:
            raise ValueError("brightness parameter required")

        if hasattr(device, "set_brightness"):
            await device.set_brightness(brightness)
        else:
            raise ValueError(f"Device {device_id} does not support brightness")

    async def _execute_set_color(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Set device color."""
        device = self.device_manager.get_device(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")

        color = params.get("color")
        if color is None:
            raise ValueError("color parameter required")

        if hasattr(device, "set_color"):
            await device.set_color(color)
        else:
            raise ValueError(f"Device {device_id} does not support color")

    async def _execute_set_temperature(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Set device color temperature."""
        device = self.device_manager.get_device(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")

        temperature = params.get("temperature")
        if temperature is None:
            raise ValueError("temperature parameter required")

        if hasattr(device, "set_color_temperature"):
            await device.set_color_temperature(temperature)
        else:
            raise ValueError(f"Device {device_id} does not support temperature")

    async def _execute_lock(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Lock a lock device."""
        device = self.device_manager.get_device(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")

        if hasattr(device, "lock"):
            await device.lock()
        else:
            raise ValueError(f"Device {device_id} is not a lock")

    async def _execute_unlock(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Unlock a lock device."""
        device = self.device_manager.get_device(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")

        if hasattr(device, "unlock"):
            await device.unlock()
        else:
            raise ValueError(f"Device {device_id} is not a lock")

    async def _execute_start_vacuum(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Start a vacuum."""
        device = self.device_manager.get_device(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")

        if hasattr(device, "start"):
            await device.start()
        else:
            raise ValueError(f"Device {device_id} is not a vacuum")

    async def _execute_stop_vacuum(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Stop a vacuum."""
        device = self.device_manager.get_device(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")

        if hasattr(device, "stop"):
            await device.stop()
        else:
            raise ValueError(f"Device {device_id} is not a vacuum")

    async def _execute_dock_vacuum(
        self, device_id: str, params: dict[str, Any]
    ) -> None:
        """Send vacuum to dock."""
        device = self.device_manager.get_device(device_id)
        if not device:
            raise ValueError(f"Device not found: {device_id}")

        if hasattr(device, "dock"):
            await device.dock()
        else:
            raise ValueError(f"Device {device_id} is not a vacuum")


def humanize_time_until(execute_at: str) -> str:
    """Convert execute_at timestamp to human-readable time until execution.

    Args:
        execute_at: ISO format timestamp

    Returns:
        Human-readable string like "in 23 minutes" or "in 2 hours"
    """
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
