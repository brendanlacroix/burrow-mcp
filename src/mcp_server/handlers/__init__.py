"""MCP tool handlers for Burrow."""

from mcp_server.handlers.discovery import handle_discover_tools, handle_get_system_status
from mcp_server.handlers.lights import LightHandlers
from mcp_server.handlers.locks import LockHandlers
from mcp_server.handlers.plugs import PlugHandlers
from mcp_server.handlers.query import QueryHandlers
from mcp_server.handlers.scenes import SceneHandlers
from mcp_server.handlers.scheduling import (
    SchedulingHandlers,
    get_pending_schedules_for_device,
)
from mcp_server.handlers.vacuum import VacuumHandlers

__all__ = [
    "handle_discover_tools",
    "handle_get_system_status",
    "LightHandlers",
    "LockHandlers",
    "PlugHandlers",
    "QueryHandlers",
    "SceneHandlers",
    "SchedulingHandlers",
    "VacuumHandlers",
    "get_pending_schedules_for_device",
]
