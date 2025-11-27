"""Room model for Burrow MCP."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class Room:
    """Represents a room in the house."""

    id: str  # "bedroom", "living_room"
    name: str  # "Bedroom", "Living Room"
    floor: int | None = None  # 1, 2, etc.
    device_ids: list[str] = field(default_factory=list)
    occupied: bool = False
    last_presence_change: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "floor": self.floor,
            "device_ids": self.device_ids,
            "occupied": self.occupied,
            "last_presence_change": (
                self.last_presence_change.isoformat() if self.last_presence_change else None
            ),
        }

    def to_summary_dict(self, lights_on: int = 0, device_count: int | None = None) -> dict[str, Any]:
        """Convert to summary dictionary for list responses."""
        return {
            "id": self.id,
            "name": self.name,
            "floor": self.floor,
            "occupied": self.occupied,
            "device_count": device_count if device_count is not None else len(self.device_ids),
            "lights_on": lights_on,
        }
