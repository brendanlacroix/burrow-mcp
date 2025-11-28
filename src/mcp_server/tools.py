"""MCP tool definitions for Burrow.

This module defines all MCP tools available for home automation control.
Tools are organized by category: discovery, query, lights, plugs, locks, vacuum, scenes.

Tool definitions follow advanced tool use best practices:
- Clear, searchable descriptions for Tool Search Tool compatibility
- Input examples showing common usage patterns
- Metadata tags for categorization and deferred loading support
"""

from mcp.types import Tool


# Tool category metadata for Tool Search Tool discovery
# Tags enable efficient tool search without loading full definitions
TOOL_CATEGORIES = {
    "discovery": {
        "name": "Discovery & Help",
        "description": "Tools for discovering available capabilities and getting help",
        "tags": ["help", "discover", "status", "system"],
        "tools": ["discover_tools", "get_system_status"],
    },
    "query": {
        "name": "Query",
        "description": "Tools for querying room, device, and presence state",
        "tags": ["query", "list", "get", "state", "rooms", "devices", "presence"],
        "tools": ["list_rooms", "get_room_state", "list_devices", "get_device_state", "get_presence"],
    },
    "lights": {
        "name": "Lighting Control",
        "description": "Tools for controlling lights (power, brightness, color, temperature)",
        "tags": ["lights", "lighting", "brightness", "color", "temperature", "power", "on", "off"],
        "tools": ["set_light_power", "set_light_brightness", "set_light_color",
                  "set_light_temperature", "set_room_lights"],
    },
    "plugs": {
        "name": "Smart Plugs",
        "description": "Tools for controlling smart plugs",
        "tags": ["plugs", "outlets", "power", "on", "off"],
        "tools": ["set_plug_power"],
    },
    "locks": {
        "name": "Door Locks",
        "description": "Tools for controlling door locks (security-sensitive)",
        "tags": ["locks", "doors", "security", "lock", "unlock"],
        "tools": ["lock_door", "unlock_door"],
    },
    "vacuum": {
        "name": "Vacuum Control",
        "description": "Tools for controlling robot vacuums",
        "tags": ["vacuum", "cleaning", "roomba", "robot", "dock"],
        "tools": ["start_vacuum", "stop_vacuum", "dock_vacuum"],
    },
    "scenes": {
        "name": "Scenes & Automation",
        "description": "Tools for predefined automation scenes",
        "tags": ["scenes", "automation", "presets", "goodnight", "movie"],
        "tools": ["list_scenes", "activate_scene"],
    },
    "scheduling": {
        "name": "Scheduling & Timers",
        "description": "Tools for scheduling future actions and managing timers",
        "tags": ["schedule", "timer", "delay", "recurring", "automation", "future", "later"],
        "tools": ["schedule_action", "list_scheduled_actions", "cancel_scheduled_action",
                  "modify_scheduled_action"],
    },
    "audit": {
        "name": "Audit & History",
        "description": "Tools for viewing device history and audit logs",
        "tags": ["audit", "history", "log", "events", "track"],
        "tools": ["get_device_history", "get_audit_log"],
    },
}


def _add_examples(schema: dict, examples: list[dict]) -> dict:
    """Add input examples to a tool schema for programmatic tool calling.

    Examples help Claude understand how to call tools correctly and enable
    more efficient programmatic tool calling by providing concrete patterns.
    """
    schema["examples"] = examples
    return schema


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
    """Get query tool definitions with input examples."""
    return [
        Tool(
            name="list_rooms",
            description="List all rooms in the house with occupancy and device counts.",
            inputSchema=_add_examples(
                {
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
                [
                    {},
                    {"floor": 1},
                    {"occupied_only": True},
                ],
            ),
        ),
        Tool(
            name="get_room_state",
            description="Get detailed state of a room including all devices and their states.",
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "room_id": {
                            "type": "string",
                            "description": "Room identifier",
                        },
                    },
                    "required": ["room_id"],
                },
                [
                    {"room_id": "living_room"},
                    {"room_id": "bedroom"},
                    {"room_id": "kitchen"},
                ],
            ),
        ),
        Tool(
            name="list_devices",
            description="List all devices. Filter by type, room, or status to narrow results.",
            inputSchema=_add_examples(
                {
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
                [
                    {},
                    {"device_type": "light"},
                    {"room_id": "living_room"},
                    {"device_type": "light", "room_id": "bedroom"},
                    {"status": "offline"},
                ],
            ),
        ),
        Tool(
            name="get_device_state",
            description="Get detailed current state of a specific device.",
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Device identifier",
                        },
                    },
                    "required": ["device_id"],
                },
                [
                    {"device_id": "living_room_lamp"},
                    {"device_id": "front_door"},
                ],
            ),
        ),
        Tool(
            name="get_presence",
            description="Get house occupancy info: who's home and which rooms are occupied.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


def get_light_tools() -> list[Tool]:
    """Get light control tool definitions with input examples."""
    return [
        Tool(
            name="set_light_power",
            description="Turn a light on or off. Use device_id from list_devices.",
            inputSchema=_add_examples(
                {
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
                [
                    {"device_id": "living_room_lamp", "on": True},
                    {"device_id": "bedroom_light", "on": False},
                ],
            ),
        ),
        Tool(
            name="set_light_brightness",
            description="Set brightness of a light (0-100%). Also turns it on if off.",
            inputSchema=_add_examples(
                {
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
                [
                    {"device_id": "living_room_lamp", "brightness": 75},
                    {"device_id": "bedroom_light", "brightness": 30},
                ],
            ),
        ),
        Tool(
            name="set_light_color",
            description="Set color of a light using hex code. For color-capable lights only.",
            inputSchema=_add_examples(
                {
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
                [
                    {"device_id": "living_room_lamp", "color": "#FF0000"},
                    {"device_id": "bedroom_light", "color": "#00FF00"},
                    {"device_id": "office_light", "color": "#FFE4B5"},
                ],
            ),
        ),
        Tool(
            name="set_light_temperature",
            description="Set color temperature in Kelvin. 2700K=warm/cozy, 4000K=neutral, 6500K=cool/daylight.",
            inputSchema=_add_examples(
                {
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
                [
                    {"device_id": "living_room_lamp", "kelvin": 2700},
                    {"device_id": "office_light", "kelvin": 5000},
                ],
            ),
        ),
        Tool(
            name="set_room_lights",
            description="Control all lights in a room at once. Efficient for whole-room changes.",
            inputSchema=_add_examples(
                {
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
                [
                    {"room_id": "living_room", "on": True, "brightness": 80},
                    {"room_id": "bedroom", "on": True, "kelvin": 2700, "brightness": 30},
                    {"room_id": "office", "on": False},
                ],
            ),
        ),
    ]


def get_plug_tools() -> list[Tool]:
    """Get plug control tool definitions with input examples."""
    return [
        Tool(
            name="set_plug_power",
            description="Turn a smart plug on or off. Controls devices plugged into the outlet.",
            inputSchema=_add_examples(
                {
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
                [
                    {"device_id": "coffee_maker_plug", "on": True},
                    {"device_id": "fan_plug", "on": False},
                ],
            ),
        ),
    ]


def get_lock_tools() -> list[Tool]:
    """Get lock control tool definitions with input examples."""
    return [
        Tool(
            name="lock_door",
            description="Lock a door. Safe operation - always allowed.",
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Lock device ID",
                        },
                    },
                    "required": ["device_id"],
                },
                [
                    {"device_id": "front_door"},
                    {"device_id": "back_door"},
                ],
            ),
        ),
        Tool(
            name="unlock_door",
            description="Unlock a door. SECURITY SENSITIVE - use with caution, verify intent first.",
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Lock device ID",
                        },
                    },
                    "required": ["device_id"],
                },
                [
                    {"device_id": "front_door"},
                ],
            ),
        ),
    ]


def get_vacuum_tools() -> list[Tool]:
    """Get vacuum control tool definitions with input examples."""
    return [
        Tool(
            name="start_vacuum",
            description="Start a vacuum cleaning cycle. Optionally target a specific room.",
            inputSchema=_add_examples(
                {
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
                [
                    {"device_id": "roomba"},
                    {"device_id": "roomba", "room_id": "kitchen"},
                ],
            ),
        ),
        Tool(
            name="stop_vacuum",
            description="Stop a vacuum mid-cycle. Vacuum will stop where it is.",
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Vacuum device ID",
                        },
                    },
                    "required": ["device_id"],
                },
                [
                    {"device_id": "roomba"},
                ],
            ),
        ),
        Tool(
            name="dock_vacuum",
            description="Send vacuum back to its charging dock.",
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Vacuum device ID",
                        },
                    },
                    "required": ["device_id"],
                },
                [
                    {"device_id": "roomba"},
                ],
            ),
        ),
    ]


def get_scene_tools() -> list[Tool]:
    """Get scene tool definitions with input examples."""
    return [
        Tool(
            name="list_scenes",
            description="List all available automation scenes. Shows scene names and what they do.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="activate_scene",
            description="Activate a predefined scene. Scenes execute multiple actions at once.",
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "scene_id": {
                            "type": "string",
                            "description": "Scene identifier (e.g. 'goodnight', 'movie')",
                        },
                    },
                    "required": ["scene_id"],
                },
                [
                    {"scene_id": "goodnight"},
                    {"scene_id": "movie"},
                    {"scene_id": "away"},
                ],
            ),
        ),
    ]


def get_scheduling_tools() -> list[Tool]:
    """Get scheduling and timer tool definitions."""
    return [
        Tool(
            name="schedule_action",
            description=(
                "Schedule a device action for later execution. "
                "Supports one-time delays ('turn off in 30 minutes') and recurring schedules "
                "('turn on daily at 7am'). The action will execute even after this conversation ends."
            ),
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Target device ID",
                        },
                        "action": {
                            "type": "string",
                            "enum": [
                                "turn_on", "turn_off", "set_brightness", "set_color",
                                "set_temperature", "lock", "unlock",
                                "start_vacuum", "stop_vacuum", "dock_vacuum",
                            ],
                            "description": "Action to perform",
                        },
                        "delay_minutes": {
                            "type": "integer",
                            "minimum": 1,
                            "description": "Execute after N minutes (use this OR at_time)",
                        },
                        "at_time": {
                            "type": "string",
                            "description": "Execute at specific time (HH:MM or ISO format)",
                        },
                        "action_params": {
                            "type": "object",
                            "description": "Parameters for the action (e.g., {brightness: 50})",
                        },
                        "recurrence": {
                            "type": "object",
                            "description": (
                                "Recurrence pattern. Types: "
                                "'daily' with 'time', "
                                "'weekly' with 'days' and 'time', "
                                "'interval' with 'minutes'"
                            ),
                        },
                        "description": {
                            "type": "string",
                            "description": "Human-readable description (auto-generated if omitted)",
                        },
                    },
                    "required": ["device_id", "action"],
                },
                [
                    {"device_id": "living_room_lamp", "action": "turn_off", "delay_minutes": 30},
                    {"device_id": "bedroom_light", "action": "turn_on", "at_time": "07:00"},
                    {
                        "device_id": "office_light",
                        "action": "turn_on",
                        "at_time": "09:00",
                        "recurrence": {"type": "weekly", "days": ["mon", "tue", "wed", "thu", "fri"], "time": "09:00"},
                    },
                    {
                        "device_id": "porch_light",
                        "action": "turn_on",
                        "recurrence": {"type": "daily", "time": "18:00"},
                    },
                ],
            ),
        ),
        Tool(
            name="list_scheduled_actions",
            description="List all pending scheduled actions. Shows what's queued to happen and when.",
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Filter by device (optional)",
                        },
                        "include_completed": {
                            "type": "boolean",
                            "description": "Include completed actions",
                            "default": False,
                        },
                    },
                },
                [
                    {},
                    {"device_id": "living_room_lamp"},
                ],
            ),
        ),
        Tool(
            name="cancel_scheduled_action",
            description="Cancel a pending scheduled action. Use list_scheduled_actions to find the schedule_id.",
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "schedule_id": {
                            "type": "string",
                            "description": "ID of the schedule to cancel",
                        },
                    },
                    "required": ["schedule_id"],
                },
                [
                    {"schedule_id": "abc123"},
                ],
            ),
        ),
        Tool(
            name="modify_scheduled_action",
            description="Change the timing of a scheduled action. Can update execution time or recurrence pattern.",
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "schedule_id": {
                            "type": "string",
                            "description": "ID of the schedule to modify",
                        },
                        "delay_minutes": {
                            "type": "integer",
                            "description": "New delay from now",
                        },
                        "at_time": {
                            "type": "string",
                            "description": "New execution time (HH:MM or ISO format)",
                        },
                        "recurrence": {
                            "type": "object",
                            "description": "New recurrence pattern (null to remove recurrence)",
                        },
                    },
                    "required": ["schedule_id"],
                },
                [
                    {"schedule_id": "abc123", "delay_minutes": 60},
                    {"schedule_id": "abc123", "at_time": "22:00"},
                ],
            ),
        ),
    ]


def get_audit_tools() -> list[Tool]:
    """Get audit and history tool definitions."""
    return [
        Tool(
            name="get_device_history",
            description=(
                "Get the history of actions performed on a device. "
                "Shows what happened, when, and whether it was user-initiated or scheduled."
            ),
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "device_id": {
                            "type": "string",
                            "description": "Device to get history for",
                        },
                        "hours": {
                            "type": "integer",
                            "description": "Hours of history to retrieve",
                            "default": 24,
                        },
                    },
                    "required": ["device_id"],
                },
                [
                    {"device_id": "living_room_lamp"},
                    {"device_id": "front_door", "hours": 48},
                ],
            ),
        ),
        Tool(
            name="get_audit_log",
            description=(
                "Get the system-wide audit log showing all actions and events. "
                "Useful for understanding what happened in the house over time."
            ),
            inputSchema=_add_examples(
                {
                    "type": "object",
                    "properties": {
                        "hours": {
                            "type": "integer",
                            "description": "Hours of history to retrieve",
                            "default": 24,
                        },
                        "event_type": {
                            "type": "string",
                            "description": "Filter by event type (e.g., 'device_changed', 'schedule_executed')",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum entries to return",
                            "default": 100,
                        },
                    },
                },
                [
                    {},
                    {"hours": 12},
                    {"event_type": "schedule_executed"},
                ],
            ),
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
        + get_scheduling_tools()
        + get_audit_tools()
    )


def get_tool_metadata() -> dict:
    """Get metadata for Tool Search Tool compatibility.

    Returns category information and tags that can be used for:
    - Tool Search Tool: Enables searching tools by keyword/tag without loading all definitions
    - Deferred Loading: Categories can be loaded on-demand
    - Programmatic Tool Calling: Tags help identify related tools for batch operations

    This metadata enables efficient tool discovery in systems with many tools.
    """
    return {
        "categories": TOOL_CATEGORIES,
        "tool_count": len(get_all_tools()),
        "tags": list(
            set(
                tag
                for cat in TOOL_CATEGORIES.values()
                for tag in cat.get("tags", [])
            )
        ),
    }


def search_tools(query: str) -> list[str]:
    """Search for tools by keyword (simulates Tool Search Tool functionality).

    Args:
        query: Search term (matched against tool names, descriptions, and category tags)

    Returns:
        List of matching tool names

    This provides a local implementation of tool search for testing and
    for use when the Tool Search Tool API feature is not available.
    """
    query_lower = query.lower()
    matches = []

    # Search by category tags first
    for cat_id, cat_info in TOOL_CATEGORIES.items():
        tags = cat_info.get("tags", [])
        if any(query_lower in tag.lower() for tag in tags):
            matches.extend(cat_info["tools"])

    # Also search tool names and descriptions
    for tool in get_all_tools():
        if query_lower in tool.name.lower() or query_lower in tool.description.lower():
            if tool.name not in matches:
                matches.append(tool.name)

    return matches
