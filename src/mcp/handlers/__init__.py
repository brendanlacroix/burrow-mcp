"""MCP tool handlers for Burrow."""

from mcp.handlers.discovery import handle_discover_tools, handle_get_system_status
from mcp.handlers.lights import LightHandlers
from mcp.handlers.locks import LockHandlers
from mcp.handlers.plugs import PlugHandlers
from mcp.handlers.query import QueryHandlers
from mcp.handlers.scenes import SceneHandlers
from mcp.handlers.vacuum import VacuumHandlers

__all__ = [
    "handle_discover_tools",
    "handle_get_system_status",
    "LightHandlers",
    "LockHandlers",
    "PlugHandlers",
    "QueryHandlers",
    "SceneHandlers",
    "VacuumHandlers",
]
