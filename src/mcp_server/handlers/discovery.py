"""Discovery and system status handlers."""

import json
from typing import Any

from devices.manager import DeviceManager
from mcp_server.tools import TOOL_CATEGORIES, get_all_tools
from models.base import DeviceStatus


async def handle_discover_tools(
    args: dict[str, Any],
    device_manager: DeviceManager,
) -> dict[str, Any]:
    """Handle the discover_tools tool.

    Returns organized information about all available tools.
    """
    category_filter = args.get("category")
    all_tools = get_all_tools()

    # Build tool lookup by name
    tool_lookup = {tool.name: tool for tool in all_tools}

    result = {
        "message": "Available home automation tools",
        "categories": [],
    }

    for cat_id, cat_info in TOOL_CATEGORIES.items():
        if category_filter and cat_id != category_filter:
            continue

        cat_tools = []
        for tool_name in cat_info["tools"]:
            tool = tool_lookup.get(tool_name)
            if tool:
                # Extract required params
                schema = tool.inputSchema
                required = schema.get("required", [])
                properties = schema.get("properties", {})

                params = []
                for prop_name, prop_info in properties.items():
                    param = {
                        "name": prop_name,
                        "type": prop_info.get("type", "any"),
                        "description": prop_info.get("description", ""),
                        "required": prop_name in required,
                    }
                    if "enum" in prop_info:
                        param["options"] = prop_info["enum"]
                    if "default" in prop_info:
                        param["default"] = prop_info["default"]
                    params.append(param)

                cat_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": params,
                })

        result["categories"].append({
            "id": cat_id,
            "name": cat_info["name"],
            "description": cat_info["description"],
            "tools": cat_tools,
        })

    # Add usage hints
    result["hints"] = {
        "getting_started": [
            "Use 'list_rooms' to see all rooms in the house",
            "Use 'list_devices' to see all connected devices",
            "Use 'get_presence' to check room occupancy",
        ],
        "common_actions": [
            "Turn off all lights in a room: use 'set_room_lights' with on=false",
            "Set mood lighting: use 'set_light_brightness' and 'set_light_temperature'",
            "Lock up at night: use 'list_scenes' and 'activate_scene' for 'goodnight' scene",
        ],
    }

    return result


async def handle_get_system_status(
    args: dict[str, Any],
    device_manager: DeviceManager,
) -> dict[str, Any]:
    """Handle the get_system_status tool.

    Returns overall system health and status.
    """
    devices = device_manager.get_devices()
    rooms = device_manager.get_rooms()

    # Count device states
    online_count = sum(1 for d in devices if d.status == DeviceStatus.ONLINE)
    offline_count = sum(1 for d in devices if d.status == DeviceStatus.OFFLINE)
    unknown_count = sum(1 for d in devices if d.status == DeviceStatus.UNKNOWN)

    # Count occupied rooms
    occupied_rooms = sum(1 for r in rooms if r.occupied)

    # Group devices by type
    by_type: dict[str, int] = {}
    for device in devices:
        type_name = device.device_type.value
        by_type[type_name] = by_type.get(type_name, 0) + 1

    # Get offline devices for troubleshooting
    offline_devices = [
        {"id": d.id, "name": d.name, "type": d.device_type.value}
        for d in devices
        if d.status == DeviceStatus.OFFLINE
    ]

    status = {
        "status": "healthy" if offline_count == 0 else "degraded",
        "summary": {
            "total_devices": len(devices),
            "online_devices": online_count,
            "offline_devices": offline_count,
            "unknown_devices": unknown_count,
            "total_rooms": len(rooms),
            "occupied_rooms": occupied_rooms,
        },
        "devices_by_type": by_type,
    }

    if offline_devices:
        status["issues"] = {
            "offline_devices": offline_devices,
            "recommendation": (
                "Check device connectivity and power. "
                "Try refreshing state with get_device_state for each offline device."
            ),
        }

    return status
