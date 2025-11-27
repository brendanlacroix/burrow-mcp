"""Tests for persistence layer."""

import asyncio
from pathlib import Path

import pytest

from persistence import StateStore


class TestStateStore:
    """Tests for StateStore."""

    @pytest.fixture
    async def store(self, tmp_path: Path) -> StateStore:
        """Create a test state store."""
        db_path = tmp_path / "test_state.db"
        store = StateStore(db_path)
        await store.initialize()
        yield store
        await store.close()

    @pytest.mark.asyncio
    async def test_initialize(self, store):
        """Test store initialization."""
        # Store should be ready to use
        assert store._db is not None

    @pytest.mark.asyncio
    async def test_save_and_load_device_state(self, store):
        """Test saving and loading device state."""
        device_id = "test_light"
        state = {"is_on": True, "brightness": 75}

        await store.save_device_state(device_id, "light", state)
        loaded = await store.load_device_state(device_id)

        assert loaded == state

    @pytest.mark.asyncio
    async def test_load_nonexistent_device_state(self, store):
        """Test loading state for unknown device."""
        loaded = await store.load_device_state("nonexistent")
        assert loaded is None

    @pytest.mark.asyncio
    async def test_load_all_device_states(self, store):
        """Test loading all device states."""
        await store.save_device_state("light_1", "light", {"is_on": True})
        await store.save_device_state("plug_1", "plug", {"is_on": False})

        all_states = await store.load_all_device_states()

        assert len(all_states) == 2
        assert all_states["light_1"]["is_on"] is True
        assert all_states["plug_1"]["is_on"] is False

    @pytest.mark.asyncio
    async def test_update_device_state(self, store):
        """Test updating existing device state."""
        device_id = "test_light"

        await store.save_device_state(device_id, "light", {"is_on": False})
        await store.save_device_state(device_id, "light", {"is_on": True})

        loaded = await store.load_device_state(device_id)
        assert loaded["is_on"] is True

    @pytest.mark.asyncio
    async def test_save_and_load_room_state(self, store):
        """Test saving and loading room state."""
        await store.save_room_state("living_room", True)
        occupied = await store.load_room_state("living_room")

        assert occupied is True

        await store.save_room_state("living_room", False)
        occupied = await store.load_room_state("living_room")

        assert occupied is False

    @pytest.mark.asyncio
    async def test_load_nonexistent_room_state(self, store):
        """Test loading state for unknown room."""
        occupied = await store.load_room_state("nonexistent")
        assert occupied is None

    @pytest.mark.asyncio
    async def test_load_all_room_states(self, store):
        """Test loading all room states."""
        await store.save_room_state("living_room", True)
        await store.save_room_state("bedroom", False)

        all_states = await store.load_all_room_states()

        assert len(all_states) == 2
        assert all_states["living_room"] is True
        assert all_states["bedroom"] is False

    @pytest.mark.asyncio
    async def test_record_device_event(self, store):
        """Test recording device events."""
        await store.record_device_event(
            "light_1",
            "power_on",
            {"brightness": 100},
        )

        history = await store.get_device_history("light_1")

        assert len(history) == 1
        assert history[0]["event_type"] == "power_on"
        assert history[0]["state"]["brightness"] == 100

    @pytest.mark.asyncio
    async def test_device_history_limit(self, store):
        """Test device history with limit."""
        for i in range(10):
            await store.record_device_event("light_1", f"event_{i}")

        history = await store.get_device_history("light_1", limit=5)
        assert len(history) == 5

    @pytest.mark.asyncio
    async def test_device_history_by_type(self, store):
        """Test filtering device history by event type."""
        await store.record_device_event("light_1", "power_on")
        await store.record_device_event("light_1", "power_off")
        await store.record_device_event("light_1", "power_on")

        history = await store.get_device_history(
            "light_1", event_type="power_on"
        )
        assert len(history) == 2
        assert all(e["event_type"] == "power_on" for e in history)

    @pytest.mark.asyncio
    async def test_record_presence_event(self, store):
        """Test recording presence events."""
        await store.record_presence_event("living_room", True, 0.95)

        history = await store.get_presence_history("living_room")

        assert len(history) == 1
        assert history[0]["occupied"] is True
        assert history[0]["confidence"] == 0.95

    @pytest.mark.asyncio
    async def test_presence_history_limit(self, store):
        """Test presence history with limit."""
        for i in range(10):
            await store.record_presence_event("living_room", i % 2 == 0)

        history = await store.get_presence_history("living_room", limit=5)
        assert len(history) == 5

    @pytest.mark.asyncio
    async def test_cleanup_old_history(self, store):
        """Test cleaning up old history."""
        # Add some events
        await store.record_device_event("light_1", "test")
        await store.record_presence_event("living_room", True)

        # Cleanup with 0 days should remove everything
        deleted = await store.cleanup_old_history(days=0)
        assert deleted == 2

        # Verify history is empty
        device_history = await store.get_device_history("light_1")
        presence_history = await store.get_presence_history("living_room")
        assert len(device_history) == 0
        assert len(presence_history) == 0

    @pytest.mark.asyncio
    async def test_concurrent_access(self, store):
        """Test concurrent access to store."""

        async def save_state(device_id: str):
            for i in range(5):
                await store.save_device_state(
                    device_id, "light", {"value": i}
                )

        # Run concurrent saves
        await asyncio.gather(
            save_state("device_1"),
            save_state("device_2"),
            save_state("device_3"),
        )

        # All states should be saved
        all_states = await store.load_all_device_states()
        assert len(all_states) == 3
