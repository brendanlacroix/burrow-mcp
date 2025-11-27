"""Tests for DeviceManager."""

import pytest

from devices.manager import DeviceManager
from models.base import DeviceStatus, DeviceType
from models.light import Light
from models.plug import Plug


class TestDeviceManager:
    """Tests for DeviceManager."""

    @pytest.mark.asyncio
    async def test_initialization(self, device_manager):
        """Test manager initialization."""
        # Check rooms were created
        rooms = device_manager.get_rooms()
        assert len(rooms) == 3
        assert device_manager.get_room("living_room") is not None
        assert device_manager.get_room("bedroom") is not None
        assert device_manager.get_room("kitchen") is not None

    @pytest.mark.asyncio
    async def test_devices_created(self, device_manager):
        """Test devices were created from config."""
        devices = device_manager.get_devices()
        assert len(devices) == 3  # 2 lights + 1 plug

        light = device_manager.get_light("light_1")
        assert light is not None
        assert light.name == "Floor Lamp"

        plug = device_manager.get_plug("plug_1")
        assert plug is not None
        assert plug.name == "TV Plug"

    @pytest.mark.asyncio
    async def test_get_devices_by_type(self, device_manager):
        """Test filtering devices by type."""
        lights = device_manager.get_lights()
        assert len(lights) == 2

        plugs = device_manager.get_plugs()
        assert len(plugs) == 1

    @pytest.mark.asyncio
    async def test_get_devices_by_room(self, device_manager):
        """Test filtering devices by room."""
        living_room_lights = device_manager.get_lights(room_id="living_room")
        assert len(living_room_lights) == 1
        assert living_room_lights[0].id == "light_1"

        bedroom_lights = device_manager.get_lights(room_id="bedroom")
        assert len(bedroom_lights) == 1
        assert bedroom_lights[0].id == "light_2"

    @pytest.mark.asyncio
    async def test_get_room_devices(self, device_manager):
        """Test getting all devices in a room."""
        devices = device_manager.get_room_devices("living_room")
        assert len(devices) == 2  # light_1 and plug_1

        device_ids = [d.id for d in devices]
        assert "light_1" in device_ids
        assert "plug_1" in device_ids

    @pytest.mark.asyncio
    async def test_device_to_response(self, device_manager):
        """Test converting device to response dict."""
        light = device_manager.get_light("light_1")
        response = device_manager.device_to_response(light)

        assert response["id"] == "light_1"
        assert response["name"] == "Floor Lamp"
        assert response["type"] == "light"
        assert response["status"] == "online"
        assert "state" in response

    @pytest.mark.asyncio
    async def test_room_to_response(self, device_manager):
        """Test converting room to response dict."""
        room = device_manager.get_room("living_room")
        response = device_manager.room_to_response(room)

        assert response["room"]["id"] == "living_room"
        assert response["room"]["name"] == "Living Room"
        assert len(response["devices"]) == 2

    @pytest.mark.asyncio
    async def test_count_lights_on(self, device_manager):
        """Test counting lights that are on."""
        # Initially all lights should be off
        count = device_manager.count_lights_on()
        assert count == 0

        # Turn on a light
        light = device_manager.get_light("light_1")
        light.is_on = True

        count = device_manager.count_lights_on()
        assert count == 1

        # Count for specific room
        count = device_manager.count_lights_on(room_id="living_room")
        assert count == 1

        count = device_manager.count_lights_on(room_id="bedroom")
        assert count == 0

    @pytest.mark.asyncio
    async def test_room_presence(self, device_manager):
        """Test room presence updates."""
        room = device_manager.get_room("living_room")
        assert room.occupied is False

        await device_manager.update_room_presence("living_room", True)
        assert room.occupied is True

        await device_manager.update_room_presence("living_room", False)
        assert room.occupied is False

    @pytest.mark.asyncio
    async def test_get_rooms_filters(self, device_manager):
        """Test room filtering."""
        # All rooms are floor 1
        rooms = device_manager.get_rooms(floor=1)
        assert len(rooms) == 3

        rooms = device_manager.get_rooms(floor=2)
        assert len(rooms) == 0

        # Set one room as occupied
        await device_manager.update_room_presence("living_room", True)

        rooms = device_manager.get_rooms(occupied_only=True)
        assert len(rooms) == 1
        assert rooms[0].id == "living_room"

    @pytest.mark.asyncio
    async def test_unknown_device(self, device_manager):
        """Test handling of unknown device."""
        device = device_manager.get_device("nonexistent")
        assert device is None

        light = device_manager.get_light("nonexistent")
        assert light is None

    @pytest.mark.asyncio
    async def test_unknown_room(self, device_manager):
        """Test handling of unknown room."""
        room = device_manager.get_room("nonexistent")
        assert room is None

        devices = device_manager.get_room_devices("nonexistent")
        assert devices == []

    @pytest.mark.asyncio
    async def test_shutdown(self, device_manager):
        """Test graceful shutdown."""
        # Turn on a light to create state
        light = device_manager.get_light("light_1")
        light.is_on = True
        light.brightness = 50

        # Should not raise
        await device_manager.shutdown()
