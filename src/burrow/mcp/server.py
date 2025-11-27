"""MCP server implementation for Burrow home automation."""

import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from burrow.config import BurrowConfig, SceneConfig, SecretsConfig
from burrow.devices.base import DeviceManager
from burrow.models.device import DeviceStatus, DeviceType, Light, Lock, Plug, Vacuum
from burrow.models.presence import PresenceState
from burrow.presence.mmwave import PresenceManager

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
        self.secrets = secrets
        self.device_manager = device_manager
        self.presence_manager = presence_manager
        self._presence_state = PresenceState()
        self.server = Server("burrow")
        self._setup_handlers()

    def _setup_handlers(self) -> None:
        """Set up MCP tool handlers."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """Return list of available tools."""
            return [
                # Query tools
                Tool(
                    name="list_rooms",
                    description="List all rooms in the house with their current state",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "floor": {
                                "type": "integer",
                                "description": "Filter by floor number (optional)",
                            },
                            "occupied_only": {
                                "type": "boolean",
                                "description": "Only return occupied rooms",
                                "default": False,
                            },
                        },
                    },
                ),
                Tool(
                    name="get_room_state",
                    description="Get detailed state of a specific room including all devices",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "room_id": {
                                "type": "string",
                                "description": "Room identifier",
                            },
                        },
                        "required": ["room_id"],
                    },
                ),
                Tool(
                    name="list_devices",
                    description="List all devices, optionally filtered by type or room",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_type": {
                                "type": "string",
                                "enum": ["light", "plug", "lock", "vacuum", "camera", "sensor"],
                                "description": "Filter by device type",
                            },
                            "room_id": {
                                "type": "string",
                                "description": "Filter by room",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["online", "offline"],
                                "description": "Filter by online status",
                            },
                        },
                    },
                ),
                Tool(
                    name="get_device_state",
                    description="Get detailed state of a specific device",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Device identifier",
                            },
                        },
                        "required": ["device_id"],
                    },
                ),
                Tool(
                    name="get_presence",
                    description="Get current presence information for the house",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
                # Light control tools
                Tool(
                    name="set_light_power",
                    description="Turn a light on or off",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Light device ID",
                            },
                            "on": {
                                "type": "boolean",
                                "description": "True to turn on, false to turn off",
                            },
                        },
                        "required": ["device_id", "on"],
                    },
                ),
                Tool(
                    name="set_light_brightness",
                    description="Set brightness of a light (also turns it on if off)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Light device ID",
                            },
                            "brightness": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 100,
                                "description": "Brightness percentage (0-100)",
                            },
                        },
                        "required": ["device_id", "brightness"],
                    },
                ),
                Tool(
                    name="set_light_color",
                    description="Set color of a light (for color-capable lights)",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Light device ID",
                            },
                            "color": {
                                "type": "string",
                                "description": "Hex color code (e.g. '#FF0000' for red) or color name",
                            },
                        },
                        "required": ["device_id", "color"],
                    },
                ),
                Tool(
                    name="set_light_temperature",
                    description="Set color temperature of a light in Kelvin",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Light device ID",
                            },
                            "kelvin": {
                                "type": "integer",
                                "minimum": 1500,
                                "maximum": 9000,
                                "description": "Color temperature in Kelvin (2700=warm, 4000=neutral, 6500=cool)",
                            },
                        },
                        "required": ["device_id", "kelvin"],
                    },
                ),
                Tool(
                    name="set_room_lights",
                    description="Control all lights in a room at once",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "room_id": {
                                "type": "string",
                                "description": "Room identifier",
                            },
                            "on": {
                                "type": "boolean",
                                "description": "Turn all lights on or off",
                            },
                            "brightness": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 100,
                                "description": "Set brightness for all lights (optional)",
                            },
                            "color": {
                                "type": "string",
                                "description": "Set color for color-capable lights (optional)",
                            },
                            "kelvin": {
                                "type": "integer",
                                "description": "Set color temperature (optional)",
                            },
                        },
                        "required": ["room_id", "on"],
                    },
                ),
                # Plug control tools
                Tool(
                    name="set_plug_power",
                    description="Turn a smart plug on or off",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Plug device ID",
                            },
                            "on": {
                                "type": "boolean",
                                "description": "True to turn on, false to turn off",
                            },
                        },
                        "required": ["device_id", "on"],
                    },
                ),
                # Lock control tools
                Tool(
                    name="lock_door",
                    description="Lock a door",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Lock device ID",
                            },
                        },
                        "required": ["device_id"],
                    },
                ),
                Tool(
                    name="unlock_door",
                    description="Unlock a door. Use with caution.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Lock device ID",
                            },
                        },
                        "required": ["device_id"],
                    },
                ),
                # Vacuum control tools
                Tool(
                    name="start_vacuum",
                    description="Start a vacuum cleaning cycle",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Vacuum device ID",
                            },
                            "room_id": {
                                "type": "string",
                                "description": "Specific room to clean (optional, if vacuum supports room mapping)",
                            },
                        },
                        "required": ["device_id"],
                    },
                ),
                Tool(
                    name="stop_vacuum",
                    description="Stop a vacuum mid-cycle",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Vacuum device ID",
                            },
                        },
                        "required": ["device_id"],
                    },
                ),
                Tool(
                    name="dock_vacuum",
                    description="Send vacuum back to its dock",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "device_id": {
                                "type": "string",
                                "description": "Vacuum device ID",
                            },
                        },
                        "required": ["device_id"],
                    },
                ),
                # Scene tools
                Tool(
                    name="list_scenes",
                    description="List all available scenes",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                    },
                ),
                Tool(
                    name="activate_scene",
                    description="Activate a predefined scene",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "scene_id": {
                                "type": "string",
                                "description": "Scene identifier (e.g. 'goodnight', 'movie', 'morning')",
                            },
                        },
                        "required": ["scene_id"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
            """Handle tool calls."""
            try:
                result = await self._handle_tool(name, arguments)
                return [TextContent(type="text", text=json.dumps(result, indent=2))]
            except Exception as e:
                logger.exception(f"Error handling tool {name}")
                return [TextContent(type="text", text=json.dumps({"error": str(e)}))]

    async def _handle_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Route tool calls to appropriate handlers."""
        # Query tools
        if name == "list_rooms":
            return await self._list_rooms(arguments)
        elif name == "get_room_state":
            return await self._get_room_state(arguments)
        elif name == "list_devices":
            return await self._list_devices(arguments)
        elif name == "get_device_state":
            return await self._get_device_state(arguments)
        elif name == "get_presence":
            return await self._get_presence(arguments)
        # Light control
        elif name == "set_light_power":
            return await self._set_light_power(arguments)
        elif name == "set_light_brightness":
            return await self._set_light_brightness(arguments)
        elif name == "set_light_color":
            return await self._set_light_color(arguments)
        elif name == "set_light_temperature":
            return await self._set_light_temperature(arguments)
        elif name == "set_room_lights":
            return await self._set_room_lights(arguments)
        # Plug control
        elif name == "set_plug_power":
            return await self._set_plug_power(arguments)
        # Lock control
        elif name == "lock_door":
            return await self._lock_door(arguments)
        elif name == "unlock_door":
            return await self._unlock_door(arguments)
        # Vacuum control
        elif name == "start_vacuum":
            return await self._start_vacuum(arguments)
        elif name == "stop_vacuum":
            return await self._stop_vacuum(arguments)
        elif name == "dock_vacuum":
            return await self._dock_vacuum(arguments)
        # Scenes
        elif name == "list_scenes":
            return await self._list_scenes(arguments)
        elif name == "activate_scene":
            return await self._activate_scene(arguments)
        else:
            return {"error": f"Unknown tool: {name}"}

    # Query tool handlers
    async def _list_rooms(self, args: dict[str, Any]) -> dict[str, Any]:
        """List all rooms."""
        floor = args.get("floor")
        occupied_only = args.get("occupied_only", False)

        rooms = self.device_manager.get_rooms(floor=floor, occupied_only=occupied_only)
        return {
            "rooms": [
                room.to_summary_dict(
                    lights_on=self.device_manager.count_lights_on(room.id),
                    device_count=len(room.device_ids),
                )
                for room in rooms
            ]
        }

    async def _get_room_state(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get detailed room state."""
        room_id = args["room_id"]
        room = self.device_manager.get_room(room_id)
        if room is None:
            return {"error": f"Room not found: {room_id}"}

        return self.device_manager.room_to_response(room)

    async def _list_devices(self, args: dict[str, Any]) -> dict[str, Any]:
        """List devices with optional filters."""
        device_type = None
        if "device_type" in args:
            try:
                device_type = DeviceType(args["device_type"])
            except ValueError:
                return {"error": f"Invalid device type: {args['device_type']}"}

        status = None
        if "status" in args:
            try:
                status = DeviceStatus(args["status"])
            except ValueError:
                return {"error": f"Invalid status: {args['status']}"}

        room_id = args.get("room_id")

        devices = self.device_manager.get_devices(
            device_type=device_type, room_id=room_id, status=status
        )
        return {"devices": [self.device_manager.device_to_response(d) for d in devices]}

    async def _get_device_state(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get detailed device state."""
        device_id = args["device_id"]
        device = self.device_manager.get_device(device_id)
        if device is None:
            return {"error": f"Device not found: {device_id}"}

        # Refresh device state
        await self.device_manager.refresh_device(device_id)
        return self.device_manager.device_to_response(device)

    async def _get_presence(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get presence state."""
        if self.presence_manager:
            return self.presence_manager.get_presence_state().to_dict()
        return self._presence_state.to_dict()

    # Light control handlers
    async def _set_light_power(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set light power state."""
        device_id = args["device_id"]
        on = args["on"]

        light = self.device_manager.get_light(device_id)
        if light is None:
            return {"error": f"Light not found: {device_id}"}

        await light.set_power(on)
        return {"success": True, "device_id": device_id, "is_on": light.is_on}

    async def _set_light_brightness(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set light brightness."""
        device_id = args["device_id"]
        brightness = args["brightness"]

        light = self.device_manager.get_light(device_id)
        if light is None:
            return {"error": f"Light not found: {device_id}"}

        await light.set_brightness(brightness)
        return {"success": True, "device_id": device_id, "brightness": light.brightness}

    async def _set_light_color(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set light color."""
        device_id = args["device_id"]
        color = args["color"]

        light = self.device_manager.get_light(device_id)
        if light is None:
            return {"error": f"Light not found: {device_id}"}

        if not light.supports_color:
            return {"error": f"Light does not support color: {device_id}"}

        await light.set_color(color)
        return {"success": True, "device_id": device_id, "color": light.color}

    async def _set_light_temperature(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set light color temperature."""
        device_id = args["device_id"]
        kelvin = args["kelvin"]

        light = self.device_manager.get_light(device_id)
        if light is None:
            return {"error": f"Light not found: {device_id}"}

        await light.set_color_temp(kelvin)
        return {"success": True, "device_id": device_id, "color_temp": light.color_temp}

    async def _set_room_lights(self, args: dict[str, Any]) -> dict[str, Any]:
        """Control all lights in a room."""
        room_id = args["room_id"]
        on = args["on"]
        brightness = args.get("brightness")
        color = args.get("color")
        kelvin = args.get("kelvin")

        room = self.device_manager.get_room(room_id)
        if room is None:
            return {"error": f"Room not found: {room_id}"}

        lights = self.device_manager.get_lights(room_id)
        if not lights:
            return {"error": f"No lights found in room: {room_id}"}

        results = []
        for light in lights:
            try:
                await light.set_power(on)
                if on and brightness is not None:
                    await light.set_brightness(brightness)
                if on and color is not None and light.supports_color:
                    await light.set_color(color)
                if on and kelvin is not None:
                    await light.set_color_temp(kelvin)
                results.append({"device_id": light.id, "success": True})
            except Exception as e:
                results.append({"device_id": light.id, "success": False, "error": str(e)})

        return {"room_id": room_id, "results": results}

    # Plug control handlers
    async def _set_plug_power(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set plug power state."""
        device_id = args["device_id"]
        on = args["on"]

        plug = self.device_manager.get_plug(device_id)
        if plug is None:
            return {"error": f"Plug not found: {device_id}"}

        await plug.set_power(on)
        return {"success": True, "device_id": device_id, "is_on": plug.is_on}

    # Lock control handlers
    async def _lock_door(self, args: dict[str, Any]) -> dict[str, Any]:
        """Lock a door."""
        device_id = args["device_id"]

        lock = self.device_manager.get_lock(device_id)
        if lock is None:
            return {"error": f"Lock not found: {device_id}"}

        await lock.lock()
        return {"success": True, "device_id": device_id, "lock_state": lock.lock_state.value}

    async def _unlock_door(self, args: dict[str, Any]) -> dict[str, Any]:
        """Unlock a door."""
        device_id = args["device_id"]

        lock = self.device_manager.get_lock(device_id)
        if lock is None:
            return {"error": f"Lock not found: {device_id}"}

        await lock.unlock()
        return {"success": True, "device_id": device_id, "lock_state": lock.lock_state.value}

    # Vacuum control handlers
    async def _start_vacuum(self, args: dict[str, Any]) -> dict[str, Any]:
        """Start vacuum cleaning."""
        device_id = args["device_id"]
        # room_id = args.get("room_id")  # For future room-specific cleaning

        vacuum = self.device_manager.get_vacuum(device_id)
        if vacuum is None:
            return {"error": f"Vacuum not found: {device_id}"}

        await vacuum.start()
        return {"success": True, "device_id": device_id, "vacuum_state": vacuum.vacuum_state.value}

    async def _stop_vacuum(self, args: dict[str, Any]) -> dict[str, Any]:
        """Stop vacuum."""
        device_id = args["device_id"]

        vacuum = self.device_manager.get_vacuum(device_id)
        if vacuum is None:
            return {"error": f"Vacuum not found: {device_id}"}

        await vacuum.stop()
        return {"success": True, "device_id": device_id, "vacuum_state": vacuum.vacuum_state.value}

    async def _dock_vacuum(self, args: dict[str, Any]) -> dict[str, Any]:
        """Send vacuum to dock."""
        device_id = args["device_id"]

        vacuum = self.device_manager.get_vacuum(device_id)
        if vacuum is None:
            return {"error": f"Vacuum not found: {device_id}"}

        await vacuum.dock()
        return {"success": True, "device_id": device_id, "vacuum_state": vacuum.vacuum_state.value}

    # Scene handlers
    async def _list_scenes(self, args: dict[str, Any]) -> dict[str, Any]:
        """List available scenes."""
        return {
            "scenes": [
                {"id": scene.id, "name": scene.name, "action_count": len(scene.actions)}
                for scene in self.config.scenes
            ]
        }

    async def _activate_scene(self, args: dict[str, Any]) -> dict[str, Any]:
        """Activate a scene."""
        scene_id = args["scene_id"]

        scene = next((s for s in self.config.scenes if s.id == scene_id), None)
        if scene is None:
            return {"error": f"Scene not found: {scene_id}"}

        results = []
        for action in scene.actions:
            try:
                result = await self._execute_scene_action(action)
                results.append(result)
            except Exception as e:
                results.append({"action": action.type, "success": False, "error": str(e)})

        return {"scene_id": scene_id, "scene_name": scene.name, "results": results}

    async def _execute_scene_action(self, action: Any) -> dict[str, Any]:
        """Execute a single scene action."""
        if action.type == "room_lights":
            room_id = action.room
            if room_id == "all":
                # Apply to all rooms
                all_results = []
                for room in self.device_manager.get_rooms():
                    result = await self._set_room_lights(
                        {
                            "room_id": room.id,
                            "on": action.on or False,
                            "brightness": action.brightness,
                            "color": action.color,
                            "kelvin": action.kelvin,
                        }
                    )
                    all_results.append(result)
                return {"action": "room_lights", "room": "all", "results": all_results}
            else:
                return await self._set_room_lights(
                    {
                        "room_id": room_id,
                        "on": action.on or False,
                        "brightness": action.brightness,
                        "color": action.color,
                        "kelvin": action.kelvin,
                    }
                )

        elif action.type == "device":
            device_id = action.device
            device = self.device_manager.get_device(device_id)
            if device is None:
                return {"action": "device", "device": device_id, "error": "Device not found"}

            if isinstance(device, Light):
                if action.on is not None:
                    await device.set_power(action.on)
                if action.brightness is not None:
                    await device.set_brightness(action.brightness)
                if action.color is not None and device.supports_color:
                    await device.set_color(action.color)
                if action.kelvin is not None:
                    await device.set_color_temp(action.kelvin)
            elif isinstance(device, Plug):
                if action.on is not None:
                    await device.set_power(action.on)

            return {"action": "device", "device": device_id, "success": True}

        elif action.type == "lock":
            device_id = action.device
            lock_action = action.action

            lock = self.device_manager.get_lock(device_id)
            if lock is None:
                return {"action": "lock", "device": device_id, "error": "Lock not found"}

            if lock_action == "lock":
                await lock.lock()
            elif lock_action == "unlock":
                await lock.unlock()

            return {"action": "lock", "device": device_id, "lock_state": lock.lock_state.value}

        return {"action": action.type, "error": "Unknown action type"}

    async def run(self) -> None:
        """Run the MCP server."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(read_stream, write_stream, self.server.create_initialization_options())


def create_server(
    config: BurrowConfig,
    secrets: SecretsConfig,
    device_manager: DeviceManager,
    presence_manager: PresenceManager | None = None,
) -> BurrowMcpServer:
    """Create a new Burrow MCP server instance."""
    return BurrowMcpServer(config, secrets, device_manager, presence_manager)
