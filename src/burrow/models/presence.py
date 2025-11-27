"""Presence state models for Burrow MCP."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RoomPresence:
    """Presence information for a single room."""

    room_id: str
    occupied: bool = False
    since: datetime | None = None
    sensor_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "room_id": self.room_id,
            "occupied": self.occupied,
            "since": self.since.isoformat() if self.since else None,
            "sensor_id": self.sensor_id,
        }


@dataclass
class PresenceState:
    """Overall presence state for the house."""

    room_states: dict[str, RoomPresence] = field(default_factory=dict)

    @property
    def anyone_home(self) -> bool:
        """Check if anyone is home (any room occupied)."""
        return any(rp.occupied for rp in self.room_states.values())

    @property
    def occupied_rooms(self) -> list[str]:
        """Get list of occupied room IDs."""
        return [room_id for room_id, rp in self.room_states.items() if rp.occupied]

    def set_room_presence(
        self, room_id: str, occupied: bool, sensor_id: str | None = None
    ) -> None:
        """Update presence for a room."""
        if room_id not in self.room_states:
            self.room_states[room_id] = RoomPresence(room_id=room_id)

        room_presence = self.room_states[room_id]
        if room_presence.occupied != occupied:
            room_presence.occupied = occupied
            room_presence.since = datetime.now()

        if sensor_id:
            room_presence.sensor_id = sensor_id

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for MCP responses."""
        return {
            "anyone_home": self.anyone_home,
            "occupied_rooms": self.occupied_rooms,
            "room_details": [rp.to_dict() for rp in self.room_states.values() if rp.occupied],
        }
