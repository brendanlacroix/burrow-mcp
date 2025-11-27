"""State persistence for Burrow MCP."""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class StateStore:
    """Persistent state storage using SQLite."""

    def __init__(self, db_path: Path | str = "burrow_state.db"):
        self.db_path = Path(db_path)
        self._db: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize the database connection and schema."""
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS device_state (
                device_id TEXT PRIMARY KEY,
                state_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS room_state (
                room_id TEXT PRIMARY KEY,
                occupied INTEGER NOT NULL DEFAULT 0,
                last_presence_change TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        await self._db.commit()
        logger.info(f"Initialized state store at {self.db_path}")

    async def close(self) -> None:
        """Close the database connection."""
        if self._db:
            await self._db.close()
            self._db = None

    async def save_device_state(self, device_id: str, state: dict[str, Any]) -> None:
        """Save device state to the database."""
        if not self._db:
            return

        async with self._lock:
            now = datetime.now().isoformat()
            await self._db.execute(
                """
                INSERT OR REPLACE INTO device_state (device_id, state_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (device_id, json.dumps(state), now),
            )
            await self._db.commit()

    async def load_device_state(self, device_id: str) -> dict[str, Any] | None:
        """Load device state from the database."""
        if not self._db:
            return None

        async with self._lock:
            cursor = await self._db.execute(
                "SELECT state_json FROM device_state WHERE device_id = ?",
                (device_id,),
            )
            row = await cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None

    async def save_room_state(
        self, room_id: str, occupied: bool, last_presence_change: datetime | None = None
    ) -> None:
        """Save room state to the database."""
        if not self._db:
            return

        async with self._lock:
            now = datetime.now().isoformat()
            lpc = last_presence_change.isoformat() if last_presence_change else None
            await self._db.execute(
                """
                INSERT OR REPLACE INTO room_state (room_id, occupied, last_presence_change, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (room_id, int(occupied), lpc, now),
            )
            await self._db.commit()

    async def load_room_state(self, room_id: str) -> dict[str, Any] | None:
        """Load room state from the database."""
        if not self._db:
            return None

        async with self._lock:
            cursor = await self._db.execute(
                "SELECT occupied, last_presence_change FROM room_state WHERE room_id = ?",
                (room_id,),
            )
            row = await cursor.fetchone()
            if row:
                return {
                    "occupied": bool(row[0]),
                    "last_presence_change": row[1],
                }
            return None

    async def set(self, key: str, value: Any) -> None:
        """Set a key-value pair."""
        if not self._db:
            return

        async with self._lock:
            now = datetime.now().isoformat()
            await self._db.execute(
                """
                INSERT OR REPLACE INTO kv_store (key, value_json, updated_at)
                VALUES (?, ?, ?)
                """,
                (key, json.dumps(value), now),
            )
            await self._db.commit()

    async def get(self, key: str, default: Any = None) -> Any:
        """Get a value by key."""
        if not self._db:
            return default

        async with self._lock:
            cursor = await self._db.execute(
                "SELECT value_json FROM kv_store WHERE key = ?",
                (key,),
            )
            row = await cursor.fetchone()
            if row:
                return json.loads(row[0])
            return default

    async def delete(self, key: str) -> bool:
        """Delete a key-value pair."""
        if not self._db:
            return False

        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM kv_store WHERE key = ?",
                (key,),
            )
            await self._db.commit()
            return cursor.rowcount > 0
