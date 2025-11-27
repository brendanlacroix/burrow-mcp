"""Tests for device models."""

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from models.base import DeviceStatus, DeviceType
from models.light import Light
from models.lock import Lock, LockState
from models.plug import Plug
from models.room import Room
from models.vacuum import Vacuum, VacuumState


# Concrete test implementations of abstract device classes
@dataclass
class ConcreteLight(Light):
    """Concrete Light for testing."""

    async def refresh(self) -> None:
        pass

    async def set_power(self, on: bool) -> None:
        self.is_on = on

    async def set_brightness(self, brightness: int) -> None:
        self.brightness = brightness

    async def set_color(self, color: str) -> None:
        self.color = color

    async def set_color_temp(self, kelvin: int) -> None:
        self.color_temp = kelvin


@dataclass
class ConcreteLock(Lock):
    """Concrete Lock for testing."""

    async def refresh(self) -> None:
        pass

    async def lock(self) -> None:
        self.lock_state = LockState.LOCKED

    async def unlock(self) -> None:
        self.lock_state = LockState.UNLOCKED


@dataclass
class ConcretePlug(Plug):
    """Concrete Plug for testing."""

    async def refresh(self) -> None:
        pass

    async def set_power(self, on: bool) -> None:
        self.is_on = on


@dataclass
class ConcreteVacuum(Vacuum):
    """Concrete Vacuum for testing."""

    async def refresh(self) -> None:
        pass

    async def start(self) -> None:
        self.vacuum_state = VacuumState.CLEANING

    async def stop(self) -> None:
        self.vacuum_state = VacuumState.PAUSED

    async def dock(self) -> None:
        self.vacuum_state = VacuumState.RETURNING


class TestLightModel:
    """Tests for Light model."""

    def test_light_creation(self):
        """Test creating a light."""
        light = ConcreteLight(id="test_light", name="Test Light", room_id="living_room")
        assert light.id == "test_light"
        assert light.name == "Test Light"
        assert light.room_id == "living_room"
        assert light.device_type == DeviceType.LIGHT
        assert light.status == DeviceStatus.UNKNOWN

    def test_light_state_dict(self, mock_light):
        """Test light state dictionary."""
        state = mock_light.to_state_dict()
        assert state["is_on"] is True
        assert state["brightness"] == 75
        assert state["color_temp"] == 4000

    def test_light_defaults(self):
        """Test light default values."""
        light = ConcreteLight(id="test", name="Test")
        assert light.is_on is False
        assert light.brightness == 0
        assert light.color_temp is None
        assert light.color is None
        # Light base class has default supports_color=True
        assert light.supports_color is True


class TestLockModel:
    """Tests for Lock model."""

    def test_lock_creation(self):
        """Test creating a lock."""
        lock = ConcreteLock(id="test_lock", name="Test Lock", room_id="front_door")
        assert lock.id == "test_lock"
        assert lock.device_type == DeviceType.LOCK
        assert lock.lock_state == LockState.UNKNOWN

    def test_lock_state_dict(self, mock_lock):
        """Test lock state dictionary."""
        state = mock_lock.to_state_dict()
        assert state["lock_state"] == "locked"

    def test_lock_states(self):
        """Test all lock states."""
        lock = ConcreteLock(id="test", name="Test")

        lock.lock_state = LockState.LOCKED
        assert lock.lock_state == LockState.LOCKED

        lock.lock_state = LockState.UNLOCKED
        assert lock.lock_state == LockState.UNLOCKED

        lock.lock_state = LockState.JAMMED
        assert lock.lock_state == LockState.JAMMED


class TestPlugModel:
    """Tests for Plug model."""

    def test_plug_creation(self):
        """Test creating a plug."""
        plug = ConcretePlug(id="test_plug", name="Test Plug", room_id="living_room")
        assert plug.id == "test_plug"
        assert plug.device_type == DeviceType.PLUG
        assert plug.is_on is False

    def test_plug_state_dict(self, mock_plug):
        """Test plug state dictionary."""
        state = mock_plug.to_state_dict()
        assert state["is_on"] is False

    def test_plug_power_monitoring(self):
        """Test plug power monitoring fields."""
        plug = ConcretePlug(id="test", name="Test")
        plug.power_watts = 150.5

        state = plug.to_state_dict()
        assert state["power_watts"] == 150.5


class TestVacuumModel:
    """Tests for Vacuum model."""

    def test_vacuum_creation(self):
        """Test creating a vacuum."""
        vacuum = ConcreteVacuum(id="test_vacuum", name="Test Vacuum")
        assert vacuum.id == "test_vacuum"
        assert vacuum.device_type == DeviceType.VACUUM
        assert vacuum.vacuum_state == VacuumState.UNKNOWN

    def test_vacuum_state_dict(self, mock_vacuum):
        """Test vacuum state dictionary."""
        state = mock_vacuum.to_state_dict()
        assert state["vacuum_state"] == "docked"
        assert state["battery_percent"] == 100

    def test_vacuum_states(self):
        """Test all vacuum states."""
        vacuum = ConcreteVacuum(id="test", name="Test")

        for state in VacuumState:
            vacuum.vacuum_state = state
            assert vacuum.vacuum_state == state


class TestRoom:
    """Tests for Room model."""

    def test_room_creation(self):
        """Test creating a room."""
        room = Room(id="living_room", name="Living Room", floor=1)
        assert room.id == "living_room"
        assert room.name == "Living Room"
        assert room.floor == 1
        assert room.occupied is False

    def test_room_to_dict(self, mock_room):
        """Test room to dictionary conversion."""
        data = mock_room.to_dict()
        assert data["id"] == "living_room"
        assert data["name"] == "Living Room"
        assert data["floor"] == 1
        assert data["occupied"] is False

    def test_room_device_ids(self):
        """Test room device ID tracking."""
        room = Room(id="test", name="Test")
        room.device_ids.append("light_1")
        room.device_ids.append("plug_1")

        assert len(room.device_ids) == 2
        assert "light_1" in room.device_ids
        assert "plug_1" in room.device_ids
