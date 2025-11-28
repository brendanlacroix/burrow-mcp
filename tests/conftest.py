"""Pytest configuration and fixtures for Burrow MCP tests."""

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import BurrowConfig, DeviceConfig, RoomConfig, SceneConfig, SecretsConfig
from devices.manager import DeviceManager
from models.base import DeviceStatus, DeviceType
from models.light import Light
from models.lock import Lock, LockState
from models.plug import Plug
from models.room import Room
from models.vacuum import Vacuum, VacuumState


# Concrete test implementations of abstract device classes
@dataclass
class TestLight(Light):
    """Concrete Light implementation for testing."""

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
class TestLock(Lock):
    """Concrete Lock implementation for testing."""

    async def refresh(self) -> None:
        pass

    async def lock(self) -> None:
        self.lock_state = LockState.LOCKED

    async def unlock(self) -> None:
        self.lock_state = LockState.UNLOCKED


@dataclass
class TestPlug(Plug):
    """Concrete Plug implementation for testing."""

    async def refresh(self) -> None:
        pass

    async def set_power(self, on: bool) -> None:
        self.is_on = on


@dataclass
class TestVacuum(Vacuum):
    """Concrete Vacuum implementation for testing."""

    async def refresh(self) -> None:
        pass

    async def start(self) -> None:
        self.vacuum_state = VacuumState.CLEANING

    async def stop(self) -> None:
        self.vacuum_state = VacuumState.PAUSED

    async def dock(self) -> None:
        self.vacuum_state = VacuumState.RETURNING


@pytest.fixture
def sample_config() -> BurrowConfig:
    """Create a sample configuration for testing."""
    return BurrowConfig(
        rooms=[
            RoomConfig(id="living_room", name="Living Room", floor=1),
            RoomConfig(id="bedroom", name="Bedroom", floor=1),
            RoomConfig(id="kitchen", name="Kitchen", floor=1),
        ],
        devices=[
            DeviceConfig(
                id="light_1",
                name="Floor Lamp",
                type="lifx",
                room="living_room",
            ),
            DeviceConfig(
                id="light_2",
                name="Ceiling Light",
                type="lifx",
                room="bedroom",
            ),
            DeviceConfig(
                id="plug_1",
                name="TV Plug",
                type="tuya_plug",
                room="living_room",
            ),
        ],
        scenes=[
            SceneConfig(id="goodnight", name="Goodnight", actions=[]),
        ],
    )


@pytest.fixture
def sample_secrets() -> SecretsConfig:
    """Create a sample secrets configuration for testing."""
    return SecretsConfig(
        tuya={"plug_1": {"local_key": "test_key"}},
        august={},
        roomba={},
        govee={},
        ring={},
        mqtt={},
    )


@pytest.fixture
def mock_light() -> TestLight:
    """Create a mock light for testing."""
    light = TestLight(
        id="test_light",
        name="Test Light",
        room_id="living_room",
    )
    light.status = DeviceStatus.ONLINE
    light.is_on = True
    light.brightness = 75
    light.color_temp = 4000
    return light


@pytest.fixture
def mock_lock() -> TestLock:
    """Create a mock lock for testing."""
    lock = TestLock(
        id="test_lock",
        name="Test Lock",
        room_id="front_door",
    )
    lock.status = DeviceStatus.ONLINE
    lock.lock_state = LockState.LOCKED
    return lock


@pytest.fixture
def mock_plug() -> TestPlug:
    """Create a mock plug for testing."""
    plug = TestPlug(
        id="test_plug",
        name="Test Plug",
        room_id="living_room",
    )
    plug.status = DeviceStatus.ONLINE
    plug.is_on = False
    return plug


@pytest.fixture
def mock_vacuum() -> TestVacuum:
    """Create a mock vacuum for testing."""
    vacuum = TestVacuum(
        id="test_vacuum",
        name="Test Vacuum",
        room_id=None,
    )
    vacuum.status = DeviceStatus.ONLINE
    vacuum.vacuum_state = VacuumState.DOCKED
    vacuum.battery_percent = 100
    return vacuum


@pytest.fixture
def mock_room() -> Room:
    """Create a mock room for testing."""
    return Room(
        id="living_room",
        name="Living Room",
        floor=1,
        occupied=False,
    )


@pytest.fixture
async def device_manager(
    sample_config: BurrowConfig,
    sample_secrets: SecretsConfig,
    tmp_path: Path,
) -> DeviceManager:
    """Create a device manager with test config."""
    db_path = tmp_path / "test_state.db"
    manager = DeviceManager(sample_config, sample_secrets, db_path=db_path)

    # Register mock factories
    async def mock_light_factory(config: DeviceConfig, secrets: SecretsConfig) -> TestLight:
        light = TestLight(id=config.id, name=config.name, room_id=config.room)
        light.status = DeviceStatus.ONLINE
        return light

    async def mock_plug_factory(config: DeviceConfig, secrets: SecretsConfig) -> TestPlug:
        plug = TestPlug(id=config.id, name=config.name, room_id=config.room)
        plug.status = DeviceStatus.ONLINE
        return plug

    manager.register_device_factory("lifx", mock_light_factory)
    manager.register_device_factory("tuya_plug", mock_plug_factory)

    await manager.initialize()
    return manager


@pytest.fixture
async def device_manager_with_vacuum(
    sample_secrets: SecretsConfig,
    tmp_path: Path,
) -> DeviceManager:
    """Create a device manager with a vacuum for testing vacuum handlers."""
    config = BurrowConfig(
        rooms=[
            RoomConfig(id="living_room", name="Living Room", floor=1),
        ],
        devices=[
            DeviceConfig(
                id="vacuum_1",
                name="Roomba",
                type="roomba",
                room=None,
            ),
        ],
        scenes=[],
    )
    db_path = tmp_path / "test_vacuum_state.db"
    manager = DeviceManager(config, sample_secrets, db_path=db_path)

    async def mock_vacuum_factory(config: DeviceConfig, secrets: SecretsConfig) -> TestVacuum:
        vacuum = TestVacuum(id=config.id, name=config.name, room_id=config.room)
        vacuum.status = DeviceStatus.ONLINE
        vacuum.vacuum_state = VacuumState.DOCKED
        vacuum.battery_percent = 100
        return vacuum

    manager.register_device_factory("roomba", mock_vacuum_factory)

    await manager.initialize()
    return manager
