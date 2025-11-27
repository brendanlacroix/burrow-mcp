"""Tests for MCP handlers."""

import pytest

from mcp_server.handlers.discovery import handle_discover_tools, handle_get_system_status
from mcp_server.tools import TOOL_CATEGORIES
from models.base import DeviceStatus


class TestDiscoveryHandlers:
    """Tests for discovery handlers."""

    @pytest.mark.asyncio
    async def test_discover_tools_all(self, device_manager):
        """Test discovering all tools."""
        result = await handle_discover_tools({}, device_manager)

        assert "categories" in result
        assert "hints" in result
        assert len(result["categories"]) == len(TOOL_CATEGORIES)

    @pytest.mark.asyncio
    async def test_discover_tools_by_category(self, device_manager):
        """Test discovering tools by category."""
        result = await handle_discover_tools(
            {"category": "lights"}, device_manager
        )

        assert len(result["categories"]) == 1
        assert result["categories"][0]["id"] == "lights"

    @pytest.mark.asyncio
    async def test_discover_tools_structure(self, device_manager):
        """Test tool discovery response structure."""
        result = await handle_discover_tools({}, device_manager)

        for category in result["categories"]:
            assert "id" in category
            assert "name" in category
            assert "description" in category
            assert "tools" in category

            for tool in category["tools"]:
                assert "name" in tool
                assert "description" in tool
                assert "parameters" in tool

    @pytest.mark.asyncio
    async def test_get_system_status_healthy(self, device_manager):
        """Test system status when all healthy."""
        result = await handle_get_system_status({}, device_manager)

        assert "status" in result
        assert "summary" in result
        assert result["summary"]["total_devices"] == 3
        assert result["summary"]["online_devices"] == 3
        assert result["summary"]["offline_devices"] == 0

    @pytest.mark.asyncio
    async def test_get_system_status_degraded(self, device_manager):
        """Test system status when some devices offline."""
        # Set a device offline
        light = device_manager.get_light("light_1")
        light.status = DeviceStatus.OFFLINE

        result = await handle_get_system_status({}, device_manager)

        assert result["status"] == "degraded"
        assert result["summary"]["offline_devices"] == 1
        assert "issues" in result
        assert len(result["issues"]["offline_devices"]) == 1

    @pytest.mark.asyncio
    async def test_get_system_status_includes_device_counts(self, device_manager):
        """Test system status includes device type counts."""
        result = await handle_get_system_status({}, device_manager)

        assert "devices_by_type" in result
        assert result["devices_by_type"]["light"] == 2
        assert result["devices_by_type"]["plug"] == 1


class TestQueryHandlers:
    """Tests for query handlers."""

    @pytest.mark.asyncio
    async def test_list_rooms(self, device_manager):
        """Test listing rooms."""
        from mcp_server.handlers.query import QueryHandlers

        handlers = QueryHandlers(device_manager, None)
        result = await handlers.list_rooms({})

        assert "rooms" in result
        assert len(result["rooms"]) == 3

    @pytest.mark.asyncio
    async def test_list_rooms_filter_floor(self, device_manager):
        """Test listing rooms filtered by floor."""
        from mcp_server.handlers.query import QueryHandlers

        handlers = QueryHandlers(device_manager, None)
        result = await handlers.list_rooms({"floor": 1})

        assert len(result["rooms"]) == 3

        result = await handlers.list_rooms({"floor": 2})
        assert len(result["rooms"]) == 0

    @pytest.mark.asyncio
    async def test_get_room_state(self, device_manager):
        """Test getting room state."""
        from mcp_server.handlers.query import QueryHandlers

        handlers = QueryHandlers(device_manager, None)
        result = await handlers.get_room_state({"room_id": "living_room"})

        assert "room" in result
        assert "devices" in result
        assert result["room"]["id"] == "living_room"
        assert len(result["devices"]) == 2

    @pytest.mark.asyncio
    async def test_get_room_state_not_found(self, device_manager):
        """Test getting state for unknown room."""
        from mcp_server.handlers.query import QueryHandlers

        handlers = QueryHandlers(device_manager, None)
        result = await handlers.get_room_state({"room_id": "nonexistent"})

        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_devices(self, device_manager):
        """Test listing devices."""
        from mcp_server.handlers.query import QueryHandlers

        handlers = QueryHandlers(device_manager, None)
        result = await handlers.list_devices({})

        assert "devices" in result
        assert len(result["devices"]) == 3

    @pytest.mark.asyncio
    async def test_list_devices_filter_type(self, device_manager):
        """Test listing devices filtered by type."""
        from mcp_server.handlers.query import QueryHandlers

        handlers = QueryHandlers(device_manager, None)
        result = await handlers.list_devices({"device_type": "light"})

        assert len(result["devices"]) == 2

    @pytest.mark.asyncio
    async def test_list_devices_filter_room(self, device_manager):
        """Test listing devices filtered by room."""
        from mcp_server.handlers.query import QueryHandlers

        handlers = QueryHandlers(device_manager, None)
        result = await handlers.list_devices({"room_id": "living_room"})

        assert len(result["devices"]) == 2

    @pytest.mark.asyncio
    async def test_get_device_state(self, device_manager):
        """Test getting device state."""
        from mcp_server.handlers.query import QueryHandlers

        handlers = QueryHandlers(device_manager, None)
        result = await handlers.get_device_state({"device_id": "light_1"})

        # Handler returns device data directly (not wrapped in {"device": ...})
        assert "id" in result
        assert result["id"] == "light_1"

    @pytest.mark.asyncio
    async def test_get_device_state_not_found(self, device_manager):
        """Test getting state for unknown device."""
        from mcp_server.handlers.query import QueryHandlers

        handlers = QueryHandlers(device_manager, None)
        result = await handlers.get_device_state({"device_id": "nonexistent"})

        assert "error" in result


class TestLightHandlers:
    """Tests for light handlers."""

    @pytest.mark.asyncio
    async def test_set_light_power_not_found(self, device_manager):
        """Test setting power for unknown light."""
        from mcp_server.handlers.lights import LightHandlers

        handlers = LightHandlers(device_manager)
        result = await handlers.set_light_power(
            {"device_id": "nonexistent", "on": True}
        )

        assert "error" in result


class TestSceneHandlers:
    """Tests for scene handlers."""

    @pytest.mark.asyncio
    async def test_list_scenes(self, device_manager, sample_config):
        """Test listing scenes."""
        from mcp_server.handlers.scenes import SceneHandlers

        handlers = SceneHandlers(sample_config, device_manager)
        result = await handlers.list_scenes({})

        assert "scenes" in result
        assert len(result["scenes"]) == 1
        assert result["scenes"][0]["id"] == "goodnight"

    @pytest.mark.asyncio
    async def test_activate_scene_not_found(self, device_manager, sample_config):
        """Test activating unknown scene."""
        from mcp_server.handlers.scenes import SceneHandlers

        handlers = SceneHandlers(sample_config, device_manager)
        result = await handlers.activate_scene({"scene_id": "nonexistent"})

        assert "error" in result
