"""Tests for the scheduling system."""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
sys.path.insert(0, "src")

from scheduling.scheduler import Scheduler, calculate_next_occurrence, humanize_time_until


class TestCalculateNextOccurrence:
    """Tests for calculate_next_occurrence function."""

    def test_interval_minutes(self):
        """Test interval recurrence pattern."""
        recurrence = {"type": "interval", "minutes": 30}
        now = datetime(2024, 1, 15, 10, 0, 0)

        result = calculate_next_occurrence(recurrence, from_time=now)

        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_interval_with_until_not_expired(self):
        """Test interval with until time that hasn't passed."""
        recurrence = {
            "type": "interval",
            "minutes": 30,
            "until": "2024-01-15T12:00:00"
        }
        now = datetime(2024, 1, 15, 10, 0, 0)

        result = calculate_next_occurrence(recurrence, from_time=now)

        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_interval_with_until_expired(self):
        """Test interval with until time that has passed."""
        recurrence = {
            "type": "interval",
            "minutes": 30,
            "until": "2024-01-15T10:00:00"
        }
        now = datetime(2024, 1, 15, 10, 0, 0)

        result = calculate_next_occurrence(recurrence, from_time=now)

        assert result is None

    def test_daily_time_not_passed(self):
        """Test daily recurrence when time hasn't passed today."""
        recurrence = {"type": "daily", "time": "18:00"}
        now = datetime(2024, 1, 15, 10, 0, 0)

        result = calculate_next_occurrence(recurrence, from_time=now)

        assert result == datetime(2024, 1, 15, 18, 0, 0)

    def test_daily_time_passed(self):
        """Test daily recurrence when time has passed today."""
        recurrence = {"type": "daily", "time": "07:00"}
        now = datetime(2024, 1, 15, 10, 0, 0)

        result = calculate_next_occurrence(recurrence, from_time=now)

        assert result == datetime(2024, 1, 16, 7, 0, 0)

    def test_weekly_same_day(self):
        """Test weekly recurrence on the same day."""
        # Jan 15, 2024 is a Monday
        recurrence = {"type": "weekly", "days": ["mon"], "time": "18:00"}
        now = datetime(2024, 1, 15, 10, 0, 0)

        result = calculate_next_occurrence(recurrence, from_time=now)

        assert result == datetime(2024, 1, 15, 18, 0, 0)

    def test_weekly_next_occurrence(self):
        """Test weekly recurrence for next week."""
        # Jan 15, 2024 is a Monday
        recurrence = {"type": "weekly", "days": ["mon"], "time": "07:00"}
        now = datetime(2024, 1, 15, 10, 0, 0)

        result = calculate_next_occurrence(recurrence, from_time=now)

        # Next Monday is Jan 22
        assert result == datetime(2024, 1, 22, 7, 0, 0)

    def test_weekly_multiple_days(self):
        """Test weekly recurrence with multiple days."""
        # Jan 15, 2024 is a Monday
        recurrence = {"type": "weekly", "days": ["wed", "fri"], "time": "18:00"}
        now = datetime(2024, 1, 15, 10, 0, 0)

        result = calculate_next_occurrence(recurrence, from_time=now)

        # Next Wednesday is Jan 17
        assert result == datetime(2024, 1, 17, 18, 0, 0)

    def test_empty_recurrence(self):
        """Test with empty recurrence returns None."""
        result = calculate_next_occurrence({})
        assert result is None

    def test_none_recurrence(self):
        """Test with None recurrence returns None."""
        result = calculate_next_occurrence(None)
        assert result is None

    def test_unknown_recurrence_type(self):
        """Test with unknown recurrence type returns None."""
        recurrence = {"type": "unknown"}
        result = calculate_next_occurrence(recurrence)
        assert result is None


class TestHumanizeTimeUntil:
    """Tests for humanize_time_until function."""

    def test_minutes_away(self):
        """Test time that is minutes away."""
        future = datetime.utcnow() + timedelta(minutes=23)
        result = humanize_time_until(future.isoformat())
        # Allow for timing differences (22-23 minutes)
        assert "minute" in result and ("22" in result or "23" in result)

    def test_hours_away(self):
        """Test time that is hours away."""
        future = datetime.utcnow() + timedelta(hours=2, minutes=10)
        result = humanize_time_until(future.isoformat())
        assert "2 hour" in result

    def test_days_away(self):
        """Test time that is days away."""
        future = datetime.utcnow() + timedelta(days=3)
        result = humanize_time_until(future.isoformat())
        # Allow for timing differences (2-3 days depending on hour rollover)
        assert "day" in result and ("2" in result or "3" in result)

    def test_less_than_minute(self):
        """Test time that is less than a minute away."""
        future = datetime.utcnow() + timedelta(seconds=30)
        result = humanize_time_until(future.isoformat())
        assert "less than a minute" in result

    def test_overdue(self):
        """Test time that has passed."""
        past = datetime.utcnow() - timedelta(minutes=5)
        result = humanize_time_until(past.isoformat())
        assert result == "overdue"

    def test_singular_day(self):
        """Test singular 'day' for 1 day."""
        future = datetime.utcnow() + timedelta(days=1, hours=1)
        result = humanize_time_until(future.isoformat())
        assert "1 day" in result
        assert "days" not in result

    def test_invalid_timestamp(self):
        """Test invalid timestamp returns unknown."""
        result = humanize_time_until("not-a-timestamp")
        assert result == "unknown"


class TestScheduler:
    """Tests for the Scheduler class."""

    @pytest.fixture
    def mock_store(self):
        """Create a mock store."""
        store = MagicMock()
        store.get_due_actions = AsyncMock(return_value=[])
        store.mark_action_executed = AsyncMock()
        store.mark_action_failed = AsyncMock()
        store.log_audit_event = AsyncMock()
        return store

    @pytest.fixture
    def mock_device_manager(self):
        """Create a mock device manager."""
        return MagicMock()

    @pytest.fixture
    def scheduler(self, mock_store, mock_device_manager):
        """Create a scheduler instance."""
        return Scheduler(
            store=mock_store,
            device_manager=mock_device_manager,
            check_interval=0.1,
        )

    @pytest.mark.asyncio
    async def test_start_stop(self, scheduler):
        """Test starting and stopping the scheduler."""
        await scheduler.start()
        assert scheduler._running is True
        assert scheduler._task is not None

        await scheduler.stop()
        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_process_due_actions_empty(self, scheduler, mock_store):
        """Test processing when no actions are due."""
        await scheduler._process_due_actions()
        mock_store.get_due_actions.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_turn_on(self, scheduler, mock_device_manager):
        """Test executing turn_on action."""
        mock_device = MagicMock()
        mock_device.set_power = AsyncMock()
        mock_device.to_state_dict = MagicMock(return_value={"is_on": True})
        mock_device.refresh = AsyncMock()
        mock_device_manager.get_device.return_value = mock_device

        await scheduler._execute_turn_on("light_1", {})

        mock_device.set_power.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_execute_turn_off(self, scheduler, mock_device_manager):
        """Test executing turn_off action."""
        mock_device = MagicMock()
        mock_device.set_power = AsyncMock()
        mock_device.to_state_dict = MagicMock(return_value={"is_on": False})
        mock_device.refresh = AsyncMock()
        mock_device_manager.get_device.return_value = mock_device

        await scheduler._execute_turn_off("light_1", {})

        mock_device.set_power.assert_called_once_with(False)

    @pytest.mark.asyncio
    async def test_execute_set_brightness(self, scheduler, mock_device_manager):
        """Test executing set_brightness action."""
        mock_device = MagicMock()
        mock_device.set_brightness = AsyncMock()
        mock_device.to_state_dict = MagicMock(return_value={"brightness": 75})
        mock_device.refresh = AsyncMock()
        mock_device_manager.get_device.return_value = mock_device

        await scheduler._execute_set_brightness("light_1", {"brightness": 75})

        mock_device.set_brightness.assert_called_once_with(75)

    @pytest.mark.asyncio
    async def test_execute_lock(self, scheduler, mock_device_manager):
        """Test executing lock action."""
        mock_device = MagicMock()
        mock_device.lock = AsyncMock()
        mock_device.to_state_dict = MagicMock(return_value={"locked": True})
        mock_device.refresh = AsyncMock()
        mock_device_manager.get_device.return_value = mock_device

        await scheduler._execute_lock("front_door", {})

        mock_device.lock.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_action_device_not_found(self, scheduler, mock_device_manager):
        """Test executing action when device not found."""
        mock_device_manager.get_device.return_value = None

        with pytest.raises(ValueError, match="Device not found"):
            await scheduler._execute_turn_on("nonexistent", {})

    @pytest.mark.asyncio
    async def test_execute_action_missing_capability(self, scheduler, mock_device_manager):
        """Test executing action when device lacks capability."""
        mock_device = MagicMock(spec=[])  # No methods
        mock_device_manager.get_device.return_value = mock_device

        with pytest.raises(ValueError, match="does not support"):
            await scheduler._execute_turn_on("light_1", {})

    @pytest.mark.asyncio
    async def test_execute_action_logs_to_audit(self, scheduler, mock_store, mock_device_manager):
        """Test that executing an action logs to audit."""
        mock_device = MagicMock()
        mock_device.set_power = AsyncMock()
        mock_device.to_state_dict = MagicMock(return_value={"is_on": True})
        mock_device.refresh = AsyncMock()
        mock_device_manager.get_device.return_value = mock_device

        action = {
            "id": "sched_123",
            "device_id": "light_1",
            "action": "turn_on",
            "action_params": {},
        }

        await scheduler._execute_action(action)

        # Check audit was logged
        mock_store.log_audit_event.assert_called_once()
        call_kwargs = mock_store.log_audit_event.call_args.kwargs
        assert call_kwargs["event_type"] == "schedule_executed"
        assert call_kwargs["device_id"] == "light_1"

    @pytest.mark.asyncio
    async def test_execute_recurring_action_reschedules(self, scheduler, mock_store, mock_device_manager):
        """Test that recurring actions get rescheduled."""
        mock_device = MagicMock()
        mock_device.set_power = AsyncMock()
        mock_device.to_state_dict = MagicMock(return_value={"is_on": True})
        mock_device.refresh = AsyncMock()
        mock_device_manager.get_device.return_value = mock_device

        action = {
            "id": "sched_123",
            "device_id": "light_1",
            "action": "turn_on",
            "action_params": {},
            "recurrence": {"type": "daily", "time": "07:00"},
        }

        await scheduler._execute_action(action)

        # Check it was rescheduled with a future time
        mock_store.mark_action_executed.assert_called_once()
        call_args = mock_store.mark_action_executed.call_args
        assert call_args[0][0] == "sched_123"
        next_time = call_args[0][1]
        assert next_time is not None
        assert next_time > datetime.utcnow()


class TestScheduleContext:
    """Tests for schedule context utilities."""

    @pytest.mark.asyncio
    async def test_get_pending_schedules_no_store(self):
        """Test getting pending schedules when store is not set."""
        from mcp_server.handlers.schedule_context import (
            _store,
            get_pending_schedules_context,
            set_store,
        )

        # Ensure store is None
        original_store = _store
        set_store(None)

        result = await get_pending_schedules_context("device_1")
        assert result == []

        # Restore original store
        set_store(original_store)

    @pytest.mark.asyncio
    async def test_add_schedule_context_no_pending(self):
        """Test adding schedule context when no pending schedules."""
        from mcp_server.handlers.schedule_context import (
            add_schedule_context,
            set_store,
        )

        mock_store = MagicMock()
        mock_store.get_pending_actions_for_device = AsyncMock(return_value=[])
        set_store(mock_store)

        response = {"success": True, "device_id": "light_1"}
        result = await add_schedule_context(response, "light_1")

        assert "pending_schedules" not in result
        assert "schedule_hint" not in result

        set_store(None)

    @pytest.mark.asyncio
    async def test_add_schedule_context_with_pending(self):
        """Test adding schedule context when there are pending schedules."""
        from mcp_server.handlers.schedule_context import (
            add_schedule_context,
            set_store,
        )

        future_time = (datetime.utcnow() + timedelta(minutes=45)).isoformat()
        mock_store = MagicMock()
        mock_store.get_pending_actions_for_device = AsyncMock(return_value=[
            {
                "id": "sched_123",
                "action": "turn_off",
                "execute_at": future_time,
                "description": "Turn off at night",
            }
        ])
        set_store(mock_store)

        response = {"success": True, "device_id": "light_1"}
        result = await add_schedule_context(response, "light_1")

        assert "pending_schedules" in result
        assert len(result["pending_schedules"]) == 1
        assert result["pending_schedules"][0]["action"] == "turn_off"
        assert "schedule_hint" in result
        assert "turn_off" in result["schedule_hint"]

        set_store(None)


class TestAuditContext:
    """Tests for audit context utilities."""

    @pytest.mark.asyncio
    async def test_log_device_action_no_store(self):
        """Test logging when store is not set."""
        from mcp_server.handlers.audit_context import (
            log_device_action,
            set_store,
        )

        set_store(None)

        # Should not raise
        await log_device_action(
            device_id="light_1",
            action="set_power",
            previous_state={"is_on": False},
            new_state={"is_on": True},
        )

    @pytest.mark.asyncio
    async def test_log_device_action_with_store(self):
        """Test logging when store is set."""
        from mcp_server.handlers.audit_context import (
            log_device_action,
            set_store,
        )

        mock_store = MagicMock()
        mock_store.log_audit_event = AsyncMock()
        set_store(mock_store)

        await log_device_action(
            device_id="light_1",
            action="set_power",
            previous_state={"is_on": False},
            new_state={"is_on": True},
            metadata={"on": True},
        )

        mock_store.log_audit_event.assert_called_once()
        call_kwargs = mock_store.log_audit_event.call_args.kwargs
        assert call_kwargs["device_id"] == "light_1"
        assert call_kwargs["action"] == "set_power"
        assert call_kwargs["event_type"] == "device_action"

        set_store(None)
