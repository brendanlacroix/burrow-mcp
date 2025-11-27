"""MCP tool definitions for Burrow.

This module defines all MCP tools available for home automation control.
Tools are organized by category: discovery, query, lights, plugs, locks, vacuum, scenes.
"""

from mcp.types import Tool


# Tool category metadata for discovery
TOOL_CATEGORIES = {
    "discovery": {
        "name": "Discovery & Help",
        "description": "Tools for discovering available capabilities and getting help",
        "tools": ["discover_tools", "get_system_status"],
    },
    "query": {
        "name": "Query",
        "description": "Tools for querying room, device, and presence state",
        "tools": ["list_rooms", "get_room_state", "list_devices", "get_device_state", "get_presence"],
    },
    "lights": {
        "name": "Lighting Control",
        "description": "Tools for controlling lights (power, brightness, color, temperature)",
        "tools": ["set_light_power", "set_light_brightness", "set_light_color",
                  "set_light_temperature", "set_room_lights"],
    },
    "plugs": {
        "name": "Smart Plugs",
        "description": "Tools for controlling smart plugs",
        "tools": ["set_plug_power"],
    },
    "locks": {
        "name": "Door Locks",
        "description": "Tools for controlling door locks (security-sensitive)",
        "tools": ["lock_door", "unlock_door"],
    },
    "vacuum": {
        "name": "Vacuum Control",
        "description": "Tools for controlling robot vacuums",
        "tools": ["start_vacuum", "stop_vacuum", "dock_vacuum"],
    },
    "scenes": {
        "name": "Scenes & Automation",
        "description": "Tools for predefined automation scenes",
        "tools": ["list_scenes", "activate_scene"],
    },
}


def get_discovery_tools() -> list[Tool]:
    """Get discovery and help tool definitions."""
    return [
        Tool(
            name="discover_tools",
            description=(
                "List all available home automation tools organized by category. "
                "Use this first to understand what actions are possible. "
                "Returns tool names, descriptions, and usage examples for each category."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": list(TOOL_CATEGORIES.keys()),
                        "description": "Filter to a specific category (optional)",
                    },
                },
            },
        ),
        Tool(
            name="get_system_status",
            description=(
                "Get overall system health and status. "
                "Returns device connectivity, error counts, and any current issues. "
                "Useful for diagnosing problems or checking if the system is working correctly."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


def get_query_tools() -> list[Tool]:
    """Get query tool definitions."""
    return [
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
    ]


def get_light_tools() -> list[Tool]:
    """Get light control tool definitions."""
    return [
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
                        "description": "Hex color code (e.g. '#FF0000' for red)",
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
                        "description": "Color temperature (2700=warm, 4000=neutral, 6500=cool)",
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
    ]


def get_plug_tools() -> list[Tool]:
    """Get plug control tool definitions."""
    return [
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
    ]


def get_lock_tools() -> list[Tool]:
    """Get lock control tool definitions."""
    return [
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
    ]


def get_vacuum_tools() -> list[Tool]:
    """Get vacuum control tool definitions."""
    return [
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
                        "description": "Specific room to clean (optional)",
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
    ]


def get_scene_tools() -> list[Tool]:
    """Get scene tool definitions."""
    return [
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
                        "description": "Scene identifier (e.g. 'goodnight', 'movie')",
                    },
                },
                "required": ["scene_id"],
            },
        ),
    ]


def get_all_tools() -> list[Tool]:
    """Get all tool definitions."""
    return (
        get_discovery_tools()
        + get_query_tools()
        + get_light_tools()
        + get_plug_tools()
        + get_lock_tools()
        + get_vacuum_tools()
        + get_scene_tools()
    )
