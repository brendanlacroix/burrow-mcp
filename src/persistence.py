"""State persistence for Burrow MCP using SQLite."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

# Default database path
DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "burrow" / "state.db"


class StateStore:
    """Persistent state storage using SQLite."""

    def __init__(self, db_path: Path | str | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the database and create tables."""
        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row

        # Create tables
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS device_state (
                device_id TEXT PRIMARY KEY,
                device_type TEXT NOT NULL,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS room_state (
                room_id TEXT PRIMARY KEY,
                occupied INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS device_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                state_json TEXT,
                timestamp TEXT NOT NULL
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_device
            ON device_history(device_id, timestamp)
        """)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS presence_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id TEXT NOT NULL,
                occupied INTEGER NOT NULL,
                confidence REAL,
                timestamp TEXT NOT NULL
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_presence_room
            ON presence_events(room_id, timestamp)
        """)

        await self._db.commit()
        logger.info(f"Initialized state database at {self.db_path}")

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    # Device state methods
    async def save_device_state(
        self,
        device_id: str,
        device_type: str,
        state: dict[str, Any],
    ) -> None:
        """Save device state to database."""
        if not self._db:
            return

        async with self._lock:
            now = datetime.utcnow().isoformat()
            state_json = json.dumps(state)

            await self._db.execute(
                """
                INSERT OR REPLACE INTO device_state
                (device_id, device_type, state_json, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (device_id, device_type, state_json, now),
            )
            await self._db.commit()

    async def load_device_state(self, device_id: str) -> dict[str, Any] | None:
        """Load device state from database."""
        if not self._db:
            return None

        async with self._lock:
            async with self._db.execute(
                "SELECT state_json FROM device_state WHERE device_id = ?",
                (device_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return json.loads(row["state_json"])
        return None

    async def load_all_device_states(self) -> dict[str, dict[str, Any]]:
        """Load all device states from database."""
        if not self._db:
            return {}

        states = {}
        async with self._lock:
            async with self._db.execute(
                "SELECT device_id, state_json FROM device_state"
            ) as cursor:
                async for row in cursor:
                    states[row["device_id"]] = json.loads(row["state_json"])
        return states

    # Room state methods
    async def save_room_state(self, room_id: str, occupied: bool) -> None:
        """Save room occupancy state."""
        if not self._db:
            return

        async with self._lock:
            now = datetime.utcnow().isoformat()
            await self._db.execute(
                """
                INSERT OR REPLACE INTO room_state
                (room_id, occupied, updated_at)
                VALUES (?, ?, ?)
                """,
                (room_id, 1 if occupied else 0, now),
            )
            await self._db.commit()

    async def load_room_state(self, room_id: str) -> bool | None:
        """Load room occupancy state."""
        if not self._db:
            return None

        async with self._lock:
            async with self._db.execute(
                "SELECT occupied FROM room_state WHERE room_id = ?",
                (room_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return bool(row["occupied"])
        return None

    async def load_all_room_states(self) -> dict[str, bool]:
        """Load all room occupancy states."""
        if not self._db:
            return {}

        states = {}
        async with self._lock:
            async with self._db.execute(
                "SELECT room_id, occupied FROM room_state"
            ) as cursor:
                async for row in cursor:
                    states[row["room_id"]] = bool(row["occupied"])
        return states

    # History methods
    async def record_device_event(
        self,
        device_id: str,
        event_type: str,
        state: dict[str, Any] | None = None,
    ) -> None:
        """Record a device event in history."""
        if not self._db:
            return

        async with self._lock:
            now = datetime.utcnow().isoformat()
            state_json = json.dumps(state) if state else None

            await self._db.execute(
                """
                INSERT INTO device_history
                (device_id, event_type, state_json, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (device_id, event_type, state_json, now),
            )
            await self._db.commit()

    async def get_device_history(
        self,
        device_id: str,
        limit: int = 100,
        event_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get device event history."""
        if not self._db:
            return []

        async with self._lock:
            if event_type:
                query = """
                    SELECT event_type, state_json, timestamp
                    FROM device_history
                    WHERE device_id = ? AND event_type = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                params = (device_id, event_type, limit)
            else:
                query = """
                    SELECT event_type, state_json, timestamp
                    FROM device_history
                    WHERE device_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                """
                params = (device_id, limit)

            history = []
            async with self._db.execute(query, params) as cursor:
                async for row in cursor:
                    event = {
                        "event_type": row["event_type"],
                        "timestamp": row["timestamp"],
                    }
                    if row["state_json"]:
                        event["state"] = json.loads(row["state_json"])
                    history.append(event)

            return history

    async def record_presence_event(
        self,
        room_id: str,
        occupied: bool,
        confidence: float | None = None,
    ) -> None:
        """Record a presence detection event."""
        if not self._db:
            return

        async with self._lock:
            now = datetime.utcnow().isoformat()

            await self._db.execute(
                """
                INSERT INTO presence_events
                (room_id, occupied, confidence, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                (room_id, 1 if occupied else 0, confidence, now),
            )
            await self._db.commit()

    async def get_presence_history(
        self,
        room_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get presence detection history for a room."""
        if not self._db:
            return []

        async with self._lock:
            history = []
            async with self._db.execute(
                """
                SELECT occupied, confidence, timestamp
                FROM presence_events
                WHERE room_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (room_id, limit),
            ) as cursor:
                async for row in cursor:
                    history.append({
                        "occupied": bool(row["occupied"]),
                        "confidence": row["confidence"],
                        "timestamp": row["timestamp"],
                    })
            return history

    # Cleanup methods
    async def cleanup_old_history(self, days: int = 7) -> int:
        """Delete history older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of rows deleted
        """
        if not self._db:
            return 0

        from datetime import timedelta

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM device_history WHERE timestamp < ?",
                (cutoff,),
            )
            device_deleted = cursor.rowcount

            cursor = await self._db.execute(
                "DELETE FROM presence_events WHERE timestamp < ?",
                (cutoff,),
            )
            presence_deleted = cursor.rowcount

            await self._db.commit()

            total = device_deleted + presence_deleted
            if total > 0:
                logger.info(f"Cleaned up {total} old history records")
            return total


# Global instance
_store: StateStore | None = None


async def get_store(db_path: Path | str | None = None) -> StateStore:
    """Get or create the global state store instance."""
    global _store

    if _store is None:
        _store = StateStore(db_path)
        await _store.initialize()

    return _store


async def close_store() -> None:
    """Close the global state store."""
    global _store

    if _store:
        await _store.close()
        _store = None
