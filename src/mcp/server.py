"""MCP server implementation for Burrow home automation."""

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from config import BurrowConfig, SecretsConfig
from devices.manager import DeviceManager
from mcp.handlers import (
    LightHandlers,
    LockHandlers,
    PlugHandlers,
    QueryHandlers,
    SceneHandlers,
    VacuumHandlers,
)
from mcp.tools import get_all_tools
from presence import PresenceManager

logger = logging.getLogger(__name__)


class BurrowMcpServer:
    """MCP server for Burrow home automation."""

    def __init__(
        self,
        config: BurrowConfig,
        secrets: SecretsConfig,
        device_manager: DeviceManager,
        presence_manager: PresenceManager | None = None,
    ):
        self.config = config
        self.device_manager = device_manager

        # Initialize handlers
        self.query = QueryHandlers(device_manager, presence_manager)
        self.lights = LightHandlers(device_manager)
        self.plugs = PlugHandlers(device_manager)
        self.locks = LockHandlers(device_manager)
        self.vacuum = VacuumHandlers(device_manager)
        self.scenes = SceneHandlers(config, device_manager)

        # Set up MCP server
        self.server = Server("burrow")
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up MCP tool handlers."""

        @self.server.list_tools()
        async def list_tools() -> list:
            return get_all_tools()

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            try:
                result = await self._handle_tool(name, arguments)
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            except Exception as e:
                logger.exception(f"Error handling tool {name}")
                return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    async def _handle_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Route tool calls to appropriate handlers."""
        # Query tools
        if name == "list_rooms":
            return await self.query.list_rooms(args)
        elif name == "get_room_state":
            return await self.query.get_room_state(args)
        elif name == "list_devices":
            return await self.query.list_devices(args)
        elif name == "get_device_state":
            return await self.query.get_device_state(args)
        elif name == "get_presence":
            return await self.query.get_presence(args)

        # Light tools
        elif name == "set_light_power":
            return await self.lights.set_light_power(args)
        elif name == "set_light_brightness":
            return await self.lights.set_light_brightness(args)
        elif name == "set_light_color":
            return await self.lights.set_light_color(args)
        elif name == "set_light_temperature":
            return await self.lights.set_light_temperature(args)
        elif name == "set_room_lights":
            return await self.lights.set_room_lights(args)

        # Plug tools
        elif name == "set_plug_power":
            return await self.plugs.set_plug_power(args)

        # Lock tools
        elif name == "lock_door":
            return await self.locks.lock_door(args)
        elif name == "unlock_door":
            return await self.locks.unlock_door(args)

        # Vacuum tools
        elif name == "start_vacuum":
            return await self.vacuum.start_vacuum(args)
        elif name == "stop_vacuum":
            return await self.vacuum.stop_vacuum(args)
        elif name == "dock_vacuum":
            return await self.vacuum.dock_vacuum(args)

        # Scene tools
        elif name == "list_scenes":
            return await self.scenes.list_scenes(args)
        elif name == "activate_scene":
            return await self.scenes.activate_scene(args)

        return {"error": f"Unknown tool: {name}"}

    async def run(self) -> None:
        """Run the MCP server."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream, write_stream, self.server.create_initialization_options()
            )


def create_server(
    config: BurrowConfig,
    secrets: SecretsConfig,
    device_manager: DeviceManager,
    presence_manager: PresenceManager | None = None,
) -> BurrowMcpServer:
    """Create a new Burrow MCP server instance."""
    return BurrowMcpServer(config, secrets, device_manager, presence_manager)
