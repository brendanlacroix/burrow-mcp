"""Discovery and system status handlers."""

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

    result: dict[str, Any] = {
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
                    param: dict[str, Any] = {
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

    Returns overall system health and status with human-readable context.
    Following Anthropic best practices: return meaningful context that helps
    agents reason about next actions rather than raw data.
    """
    devices = device_manager.get_devices()
    rooms = device_manager.get_rooms()

    # Count device states
    online_count = sum(1 for d in devices if d.status == DeviceStatus.ONLINE)
    offline_count = sum(1 for d in devices if d.status == DeviceStatus.OFFLINE)
    unknown_count = sum(1 for d in devices if d.status == DeviceStatus.UNKNOWN)

    # Count occupied rooms
    occupied_rooms = [r for r in rooms if r.occupied]
    lights_on = sum(device_manager.count_lights_on(r.id) for r in rooms)

    # Group devices by type
    by_type: dict[str, int] = {}
    for device in devices:
        type_name = device.device_type.value
        by_type[type_name] = by_type.get(type_name, 0) + 1

    # Get health monitoring data
    health_summary = device_manager.get_health_summary()
    unhealthy_device_ids = device_manager.get_unhealthy_devices()

    # Get offline and unhealthy devices for troubleshooting
    offline_devices = [
        {"id": d.id, "name": d.name, "type": d.device_type.value, "room": d.room_id}
        for d in devices
        if d.status == DeviceStatus.OFFLINE
    ]

    # Get devices with health issues (may overlap with offline)
    unhealthy_devices = []
    for device_id in unhealthy_device_ids:
        device = device_manager.get_device(device_id)
        if device:
            health = device_manager.get_device_health(device_id)
            unhealthy_devices.append({
                "id": device.id,
                "name": device.name,
                "type": device.device_type.value,
                "consecutive_failures": health.consecutive_failures if health else 0,
                "failure_rate": round(health.failure_rate, 3) if health else 0,
            })

    # Build human-readable summary
    unhealthy_count = len(unhealthy_device_ids)
    if offline_count == 0 and unhealthy_count == 0:
        status_text = "All systems operational"
        status_code = "healthy"
    elif offline_count == 1 and unhealthy_count <= 1:
        status_text = f"1 device offline: {offline_devices[0]['name']}"
        status_code = "degraded"
    elif unhealthy_count > offline_count:
        status_text = f"{unhealthy_count} devices experiencing issues"
        status_code = "degraded"
    else:
        status_text = f"{offline_count} devices offline"
        status_code = "degraded"

    # Build presence summary
    if occupied_rooms:
        presence_text = f"Occupied: {', '.join(r.name for r in occupied_rooms)}"
    else:
        presence_text = "No rooms currently occupied"

    status: dict[str, Any] = {
        "status": status_code,
        "status_text": status_text,
        "summary": {
            "total_devices": len(devices),
            "online_devices": online_count,
            "offline_devices": offline_count,
            "unknown_devices": unknown_count,
            "unhealthy_devices": unhealthy_count,
            "total_rooms": len(rooms),
            "occupied_rooms": len(occupied_rooms),
            "lights_on": lights_on,
        },
        "presence": presence_text,
        "devices_by_type": by_type,
        "health": {
            "total_monitored": health_summary.get("total_devices", 0),
            "healthy": health_summary.get("healthy_devices", 0),
            "unhealthy": health_summary.get("unhealthy_devices", 0),
        },
    }

    # Add issues section if there are problems
    issues: dict[str, Any] = {}
    if offline_devices:
        issues["offline_devices"] = offline_devices
    if unhealthy_devices:
        # Only include unhealthy devices not already in offline list
        offline_ids = {d["id"] for d in offline_devices}
        additional_unhealthy = [d for d in unhealthy_devices if d["id"] not in offline_ids]
        if additional_unhealthy:
            issues["unstable_devices"] = additional_unhealthy

    if issues:
        issues["recommendation"] = (
            "Check device connectivity and power. "
            "Use 'get_device_state' with device_id to attempt refresh. "
            "Devices with high failure rates may need troubleshooting."
        )
        status["issues"] = issues

    # Add suggested next actions based on context
    suggestions = []
    if offline_count > 0:
        suggestions.append(f"Check offline devices: {', '.join(d['id'] for d in offline_devices)}")
    if unhealthy_count > offline_count:
        additional_ids = [d["id"] for d in unhealthy_devices if d["id"] not in {o["id"] for o in offline_devices}]
        if additional_ids:
            suggestions.append(f"Monitor unstable devices: {', '.join(additional_ids)}")
    if lights_on > 0 and not occupied_rooms:
        suggestions.append("Lights are on but no rooms occupied - consider turning them off")
    if suggestions:
        status["suggested_actions"] = suggestions

    return status
