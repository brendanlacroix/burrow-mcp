"""MCP server implementation for Burrow home automation."""

import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent

from config import BurrowConfig, SecretsConfig
from devices.manager import DeviceManager
from mcp_server.handlers import (
    LightHandlers,
    LockHandlers,
    PlugHandlers,
    QueryHandlers,
    SceneHandlers,
    SchedulingHandlers,
    VacuumHandlers,
    handle_discover_tools,
    handle_get_system_status,
)
from mcp_server.handlers.schedule_context import set_store as set_schedule_context_store
from mcp_server.tools import get_all_tools
from persistence import StateStore
from presence import PresenceManager
from utils.errors import (
    DEFAULT_HANDLER_TIMEOUT,
    ErrorCategory,
    ToolError,
    classify_exception,
    generate_request_id,
    get_recovery_suggestion,
)

logger = logging.getLogger(__name__)

# Timeout for tool handler execution
TOOL_TIMEOUT = DEFAULT_HANDLER_TIMEOUT


class BurrowMcpServer:
    """MCP server for Burrow home automation."""

    def __init__(
        self,
        config: BurrowConfig,
        secrets: SecretsConfig,
        device_manager: DeviceManager,
        presence_manager: PresenceManager | None = None,
        store: StateStore | None = None,
    ):
        self.config = config
        self.device_manager = device_manager
        self.store = store

        # Initialize handlers
        self.query = QueryHandlers(device_manager, presence_manager)
        self.lights = LightHandlers(device_manager)
        self.plugs = PlugHandlers(device_manager)
        self.locks = LockHandlers(device_manager)
        self.vacuum = VacuumHandlers(device_manager)
        self.scenes = SceneHandlers(config, device_manager)

        # Initialize scheduling handlers if store is available
        if store:
            self.scheduling = SchedulingHandlers(device_manager, store)
            # Enable schedule context checking for device handlers
            set_schedule_context_store(store)
        else:
            self.scheduling = None

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
            request_id = generate_request_id()
            device_id = arguments.get("device_id")

            logger.info(
                f"[{request_id}] Tool call: {name} "
                f"(device={device_id or 'N/A'})"
            )

            try:
                # Execute with timeout protection
                async with asyncio.timeout(TOOL_TIMEOUT):
                    result = await self._handle_tool(name, arguments)

                # Add request_id to successful responses for tracing
                if isinstance(result, dict) and "error" not in result:
                    result["request_id"] = request_id

                logger.info(f"[{request_id}] Tool {name} completed successfully")
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

            except asyncio.TimeoutError:
                logger.error(f"[{request_id}] Tool {name} timed out after {TOOL_TIMEOUT}s")
                error = ToolError(
                    category=ErrorCategory.TIMEOUT,
                    message=f"Operation timed out after {TOOL_TIMEOUT} seconds",
                    device_id=device_id,
                    request_id=request_id,
                    recovery=get_recovery_suggestion(ErrorCategory.TIMEOUT),
                )
                return [TextContent(type="text", text=json.dumps(error.to_dict(), indent=2))]

            except Exception as e:
                logger.exception(f"[{request_id}] Error handling tool {name}: {e}")
                error = classify_exception(e, device_id)
                error.request_id = request_id
                return [TextContent(type="text", text=json.dumps(error.to_dict(), indent=2))]

    async def _handle_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Route tool calls to appropriate handlers."""
        # Discovery tools
        if name == "discover_tools":
            return await handle_discover_tools(args, self.device_manager)
        elif name == "get_system_status":
            return await handle_get_system_status(args, self.device_manager)

        # Query tools
        elif name == "list_rooms":
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

        # Scheduling tools
        elif name == "schedule_action":
            if not self.scheduling:
                return {"error": "Scheduling not available (store not initialized)"}
            return await self.scheduling.schedule_action(args)
        elif name == "list_scheduled_actions":
            if not self.scheduling:
                return {"error": "Scheduling not available (store not initialized)"}
            return await self.scheduling.list_scheduled_actions(args)
        elif name == "cancel_scheduled_action":
            if not self.scheduling:
                return {"error": "Scheduling not available (store not initialized)"}
            return await self.scheduling.cancel_scheduled_action(args)
        elif name == "modify_scheduled_action":
            if not self.scheduling:
                return {"error": "Scheduling not available (store not initialized)"}
            return await self.scheduling.modify_scheduled_action(args)

        # Audit tools
        elif name == "get_device_history":
            if not self.scheduling:
                return {"error": "Audit not available (store not initialized)"}
            return await self.scheduling.get_device_history(args)
        elif name == "get_audit_log":
            if not self.scheduling:
                return {"error": "Audit not available (store not initialized)"}
            return await self.scheduling.get_audit_log(args)

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
    store: StateStore | None = None,
) -> BurrowMcpServer:
    """Create a new Burrow MCP server instance."""
    return BurrowMcpServer(config, secrets, device_manager, presence_manager, store)
