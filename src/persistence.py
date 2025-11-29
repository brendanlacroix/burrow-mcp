"""State persistence for Burrow MCP using SQLite."""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
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

        # Scheduled actions table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_actions (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                action TEXT NOT NULL,
                action_params TEXT,
                execute_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                recurrence TEXT,
                last_executed_at TEXT,
                status TEXT DEFAULT 'pending',
                created_by TEXT,
                description TEXT
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_scheduled_execute
            ON scheduled_actions(execute_at, status)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_scheduled_device
            ON scheduled_actions(device_id, status)
        """)

        # Audit log table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                device_id TEXT,
                source TEXT,
                action TEXT,
                previous_state TEXT,
                new_state TEXT,
                schedule_id TEXT,
                metadata TEXT
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_timestamp
            ON audit_log(timestamp)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_device
            ON audit_log(device_id, timestamp)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_type
            ON audit_log(event_type, timestamp)
        """)

        # Viewing history table for media devices
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS viewing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                app TEXT NOT NULL,
                title TEXT,
                series_name TEXT,
                season INTEGER,
                episode INTEGER,
                media_type TEXT,
                genre TEXT,
                duration INTEGER,
                watched_duration INTEGER,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                completed INTEGER DEFAULT 0
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_viewing_device
            ON viewing_history(device_id, started_at)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_viewing_app
            ON viewing_history(app, started_at)
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_viewing_title
            ON viewing_history(title, series_name)
        """)

        # User preferences/ratings table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS content_preferences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                series_name TEXT,
                app TEXT,
                genre TEXT,
                rating INTEGER,
                liked INTEGER,
                updated_at TEXT NOT NULL,
                UNIQUE(title, series_name, app)
            )
        """)

        # Followed shows table - for tracking currently airing shows
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS followed_shows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                series_name TEXT NOT NULL UNIQUE,
                tmdb_id INTEGER,
                app TEXT,
                status TEXT,
                last_watched_season INTEGER,
                last_watched_episode INTEGER,
                added_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_followed_shows_name
            ON followed_shows(series_name)
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

    # Scheduled actions methods
    async def create_scheduled_action(
        self,
        device_id: str,
        action: str,
        execute_at: datetime,
        action_params: dict[str, Any] | None = None,
        recurrence: dict[str, Any] | None = None,
        created_by: str | None = None,
        description: str | None = None,
    ) -> str:
        """Create a scheduled action.

        Args:
            device_id: Target device ID
            action: Action to perform (e.g., "turn_off", "set_brightness")
            execute_at: When to execute
            action_params: Parameters for the action
            recurrence: Recurrence pattern (None for one-time)
            created_by: Source that created this schedule
            description: Human-readable description

        Returns:
            Schedule ID
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        schedule_id = str(uuid.uuid4())[:12]
        now = datetime.utcnow().isoformat()

        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO scheduled_actions
                (id, device_id, action, action_params, execute_at, created_at,
                 recurrence, status, created_by, description)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    schedule_id,
                    device_id,
                    action,
                    json.dumps(action_params) if action_params else None,
                    execute_at.isoformat(),
                    now,
                    json.dumps(recurrence) if recurrence else None,
                    created_by,
                    description,
                ),
            )
            await self._db.commit()

        logger.info(f"Created scheduled action {schedule_id}: {action} on {device_id}")
        return schedule_id

    async def get_scheduled_action(self, schedule_id: str) -> dict[str, Any] | None:
        """Get a scheduled action by ID."""
        if not self._db:
            return None

        async with self._lock:
            async with self._db.execute(
                "SELECT * FROM scheduled_actions WHERE id = ?",
                (schedule_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return self._row_to_schedule(row)
        return None

    async def get_due_actions(self) -> list[dict[str, Any]]:
        """Get all actions that are due to execute."""
        if not self._db:
            return []

        now = datetime.utcnow().isoformat()
        actions = []

        async with self._lock:
            async with self._db.execute(
                """
                SELECT * FROM scheduled_actions
                WHERE execute_at <= ? AND status = 'pending'
                ORDER BY execute_at
                """,
                (now,),
            ) as cursor:
                async for row in cursor:
                    actions.append(self._row_to_schedule(row))

        return actions

    async def get_pending_actions_for_device(
        self, device_id: str
    ) -> list[dict[str, Any]]:
        """Get pending scheduled actions for a specific device."""
        if not self._db:
            return []

        now = datetime.utcnow().isoformat()
        actions = []

        async with self._lock:
            async with self._db.execute(
                """
                SELECT * FROM scheduled_actions
                WHERE device_id = ? AND status = 'pending' AND execute_at > ?
                ORDER BY execute_at
                """,
                (device_id, now),
            ) as cursor:
                async for row in cursor:
                    actions.append(self._row_to_schedule(row))

        return actions

    async def get_all_pending_actions(
        self, device_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get all pending scheduled actions."""
        if not self._db:
            return []

        actions = []

        async with self._lock:
            if device_id:
                query = """
                    SELECT * FROM scheduled_actions
                    WHERE status = 'pending' AND device_id = ?
                    ORDER BY execute_at
                """
                params = (device_id,)
            else:
                query = """
                    SELECT * FROM scheduled_actions
                    WHERE status = 'pending'
                    ORDER BY execute_at
                """
                params = ()

            async with self._db.execute(query, params) as cursor:
                async for row in cursor:
                    actions.append(self._row_to_schedule(row))

        return actions

    async def mark_action_executed(
        self, schedule_id: str, next_execute_at: datetime | None = None
    ) -> None:
        """Mark an action as executed.

        For recurring actions, updates execute_at to next occurrence.
        For one-time actions, marks as completed.
        """
        if not self._db:
            return

        now = datetime.utcnow().isoformat()

        async with self._lock:
            if next_execute_at:
                # Recurring: update next execution time
                await self._db.execute(
                    """
                    UPDATE scheduled_actions
                    SET last_executed_at = ?, execute_at = ?
                    WHERE id = ?
                    """,
                    (now, next_execute_at.isoformat(), schedule_id),
                )
            else:
                # One-time: mark completed
                await self._db.execute(
                    """
                    UPDATE scheduled_actions
                    SET status = 'completed', last_executed_at = ?
                    WHERE id = ?
                    """,
                    (now, schedule_id),
                )
            await self._db.commit()

    async def mark_action_failed(self, schedule_id: str, error: str) -> None:
        """Mark an action as failed."""
        if not self._db:
            return

        async with self._lock:
            await self._db.execute(
                """
                UPDATE scheduled_actions
                SET status = 'failed'
                WHERE id = ?
                """,
                (schedule_id,),
            )
            await self._db.commit()

    async def cancel_scheduled_action(self, schedule_id: str) -> bool:
        """Cancel a scheduled action."""
        if not self._db:
            return False

        async with self._lock:
            cursor = await self._db.execute(
                """
                UPDATE scheduled_actions
                SET status = 'cancelled'
                WHERE id = ? AND status = 'pending'
                """,
                (schedule_id,),
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def update_scheduled_action(
        self,
        schedule_id: str,
        execute_at: datetime | None = None,
        recurrence: dict[str, Any] | None = None,
    ) -> bool:
        """Update a scheduled action."""
        if not self._db:
            return False

        updates = []
        params = []

        if execute_at:
            updates.append("execute_at = ?")
            params.append(execute_at.isoformat())

        if recurrence is not None:
            updates.append("recurrence = ?")
            params.append(json.dumps(recurrence) if recurrence else None)

        if not updates:
            return False

        params.append(schedule_id)

        async with self._lock:
            cursor = await self._db.execute(
                f"""
                UPDATE scheduled_actions
                SET {', '.join(updates)}
                WHERE id = ? AND status = 'pending'
                """,
                params,
            )
            await self._db.commit()
            return cursor.rowcount > 0

    def _row_to_schedule(self, row: aiosqlite.Row) -> dict[str, Any]:
        """Convert a database row to a schedule dict."""
        schedule = {
            "id": row["id"],
            "device_id": row["device_id"],
            "action": row["action"],
            "execute_at": row["execute_at"],
            "created_at": row["created_at"],
            "status": row["status"],
        }

        if row["action_params"]:
            schedule["action_params"] = json.loads(row["action_params"])

        if row["recurrence"]:
            schedule["recurrence"] = json.loads(row["recurrence"])

        if row["last_executed_at"]:
            schedule["last_executed_at"] = row["last_executed_at"]

        if row["created_by"]:
            schedule["created_by"] = row["created_by"]

        if row["description"]:
            schedule["description"] = row["description"]

        return schedule

    # Audit log methods
    async def log_audit_event(
        self,
        event_type: str,
        device_id: str | None = None,
        source: str | None = None,
        action: str | None = None,
        previous_state: dict[str, Any] | None = None,
        new_state: dict[str, Any] | None = None,
        schedule_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Log an audit event.

        Args:
            event_type: Type of event (e.g., "device_changed", "schedule_created")
            device_id: Affected device ID
            source: Source of the event (e.g., "user:claude", "schedule:abc123")
            action: Action performed
            previous_state: State before the action
            new_state: State after the action
            schedule_id: Related schedule ID if applicable
            metadata: Additional context

        Returns:
            Audit log entry ID
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        entry_id = str(uuid.uuid4())[:12]
        now = datetime.utcnow().isoformat()

        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO audit_log
                (id, timestamp, event_type, device_id, source, action,
                 previous_state, new_state, schedule_id, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    now,
                    event_type,
                    device_id,
                    source,
                    action,
                    json.dumps(previous_state) if previous_state else None,
                    json.dumps(new_state) if new_state else None,
                    schedule_id,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            await self._db.commit()

        return entry_id

    async def get_audit_log(
        self,
        hours: int = 24,
        device_id: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get audit log entries.

        Args:
            hours: Get entries from last N hours
            device_id: Filter by device ID
            event_type: Filter by event type
            limit: Maximum entries to return

        Returns:
            List of audit log entries
        """
        if not self._db:
            return []

        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

        conditions = ["timestamp >= ?"]
        params: list[Any] = [cutoff]

        if device_id:
            conditions.append("device_id = ?")
            params.append(device_id)

        if event_type:
            conditions.append("event_type = ?")
            params.append(event_type)

        params.append(limit)

        entries = []
        async with self._lock:
            async with self._db.execute(
                f"""
                SELECT * FROM audit_log
                WHERE {' AND '.join(conditions)}
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                params,
            ) as cursor:
                async for row in cursor:
                    entry = {
                        "id": row["id"],
                        "timestamp": row["timestamp"],
                        "event_type": row["event_type"],
                    }

                    if row["device_id"]:
                        entry["device_id"] = row["device_id"]
                    if row["source"]:
                        entry["source"] = row["source"]
                    if row["action"]:
                        entry["action"] = row["action"]
                    if row["previous_state"]:
                        entry["previous_state"] = json.loads(row["previous_state"])
                    if row["new_state"]:
                        entry["new_state"] = json.loads(row["new_state"])
                    if row["schedule_id"]:
                        entry["schedule_id"] = row["schedule_id"]
                    if row["metadata"]:
                        entry["metadata"] = json.loads(row["metadata"])

                    entries.append(entry)

        return entries

    async def get_device_audit_history(
        self, device_id: str, hours: int = 24, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Get audit history for a specific device."""
        return await self.get_audit_log(
            hours=hours, device_id=device_id, limit=limit
        )

    # Viewing history methods
    async def record_viewing_session(
        self,
        device_id: str,
        app: str,
        title: str | None = None,
        series_name: str | None = None,
        season: int | None = None,
        episode: int | None = None,
        media_type: str | None = None,
        genre: str | None = None,
        duration: int | None = None,
    ) -> int:
        """Record start of a viewing session.

        Returns the session ID for updating when viewing ends.
        """
        if not self._db:
            raise RuntimeError("Database not initialized")

        now = datetime.utcnow().isoformat()

        async with self._lock:
            cursor = await self._db.execute(
                """
                INSERT INTO viewing_history
                (device_id, app, title, series_name, season, episode,
                 media_type, genre, duration, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    app,
                    title,
                    series_name,
                    season,
                    episode,
                    media_type,
                    genre,
                    duration,
                    now,
                ),
            )
            await self._db.commit()
            return cursor.lastrowid or 0

    async def update_viewing_session(
        self,
        session_id: int,
        watched_duration: int | None = None,
        completed: bool = False,
    ) -> None:
        """Update a viewing session when it ends or content changes."""
        if not self._db:
            return

        now = datetime.utcnow().isoformat()

        async with self._lock:
            await self._db.execute(
                """
                UPDATE viewing_history
                SET ended_at = ?, watched_duration = ?, completed = ?
                WHERE id = ?
                """,
                (now, watched_duration, 1 if completed else 0, session_id),
            )
            await self._db.commit()

    async def get_viewing_history(
        self,
        device_id: str | None = None,
        app: str | None = None,
        days: int = 30,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get viewing history, optionally filtered by device or app."""
        if not self._db:
            return []

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        conditions = ["started_at >= ?"]
        params: list[Any] = [cutoff]

        if device_id:
            conditions.append("device_id = ?")
            params.append(device_id)

        if app:
            conditions.append("app = ?")
            params.append(app)

        params.append(limit)

        history = []
        async with self._lock:
            async with self._db.execute(
                f"""
                SELECT * FROM viewing_history
                WHERE {' AND '.join(conditions)}
                ORDER BY started_at DESC
                LIMIT ?
                """,
                params,
            ) as cursor:
                async for row in cursor:
                    entry = {
                        "id": row["id"],
                        "device_id": row["device_id"],
                        "app": row["app"],
                        "started_at": row["started_at"],
                    }

                    if row["title"]:
                        entry["title"] = row["title"]
                    if row["series_name"]:
                        entry["series_name"] = row["series_name"]
                    if row["season"]:
                        entry["season"] = row["season"]
                    if row["episode"]:
                        entry["episode"] = row["episode"]
                    if row["media_type"]:
                        entry["media_type"] = row["media_type"]
                    if row["genre"]:
                        entry["genre"] = row["genre"]
                    if row["duration"]:
                        entry["duration"] = row["duration"]
                    if row["watched_duration"]:
                        entry["watched_duration"] = row["watched_duration"]
                    if row["ended_at"]:
                        entry["ended_at"] = row["ended_at"]
                    entry["completed"] = bool(row["completed"])

                    history.append(entry)

        return history

    async def get_viewing_stats(
        self, days: int = 30
    ) -> dict[str, Any]:
        """Get aggregated viewing statistics."""
        if not self._db:
            return {}

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        stats: dict[str, Any] = {
            "by_app": {},
            "by_genre": {},
            "by_media_type": {},
            "total_sessions": 0,
            "total_watch_time": 0,
        }

        async with self._lock:
            # Count by app
            async with self._db.execute(
                """
                SELECT app, COUNT(*) as count, SUM(watched_duration) as total_time
                FROM viewing_history
                WHERE started_at >= ?
                GROUP BY app
                ORDER BY count DESC
                """,
                (cutoff,),
            ) as cursor:
                async for row in cursor:
                    stats["by_app"][row["app"]] = {
                        "count": row["count"],
                        "total_time": row["total_time"] or 0,
                    }
                    stats["total_sessions"] += row["count"]
                    stats["total_watch_time"] += row["total_time"] or 0

            # Count by genre
            async with self._db.execute(
                """
                SELECT genre, COUNT(*) as count
                FROM viewing_history
                WHERE started_at >= ? AND genre IS NOT NULL
                GROUP BY genre
                ORDER BY count DESC
                """,
                (cutoff,),
            ) as cursor:
                async for row in cursor:
                    stats["by_genre"][row["genre"]] = row["count"]

            # Count by media type
            async with self._db.execute(
                """
                SELECT media_type, COUNT(*) as count
                FROM viewing_history
                WHERE started_at >= ? AND media_type IS NOT NULL
                GROUP BY media_type
                ORDER BY count DESC
                """,
                (cutoff,),
            ) as cursor:
                async for row in cursor:
                    stats["by_media_type"][row["media_type"]] = row["count"]

        return stats

    async def get_recently_watched(
        self, limit: int = 20, unique_titles: bool = True
    ) -> list[dict[str, Any]]:
        """Get recently watched content.

        Args:
            limit: Maximum number of items to return
            unique_titles: If True, only return unique titles (most recent viewing)
        """
        if not self._db:
            return []

        items = []
        async with self._lock:
            if unique_titles:
                # Get unique titles by most recent viewing
                async with self._db.execute(
                    """
                    SELECT app, title, series_name, season, episode, media_type, genre,
                           MAX(started_at) as last_watched, COUNT(*) as watch_count
                    FROM viewing_history
                    WHERE title IS NOT NULL
                    GROUP BY COALESCE(series_name, title)
                    ORDER BY last_watched DESC
                    LIMIT ?
                    """,
                    (limit,),
                ) as cursor:
                    async for row in cursor:
                        item = {
                            "app": row["app"],
                            "last_watched": row["last_watched"],
                            "watch_count": row["watch_count"],
                        }
                        if row["title"]:
                            item["title"] = row["title"]
                        if row["series_name"]:
                            item["series_name"] = row["series_name"]
                        if row["season"]:
                            item["season"] = row["season"]
                        if row["episode"]:
                            item["episode"] = row["episode"]
                        if row["media_type"]:
                            item["media_type"] = row["media_type"]
                        if row["genre"]:
                            item["genre"] = row["genre"]

                        items.append(item)
            else:
                # Get all recent viewing
                history = await self.get_viewing_history(limit=limit)
                items = history

        return items

    async def get_frequently_watched(
        self, days: int = 90, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get most frequently watched shows/content."""
        if not self._db:
            return []

        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()

        items = []
        async with self._lock:
            async with self._db.execute(
                """
                SELECT app, title, series_name, media_type, genre,
                       COUNT(*) as watch_count,
                       SUM(watched_duration) as total_time,
                       MAX(started_at) as last_watched
                FROM viewing_history
                WHERE started_at >= ? AND title IS NOT NULL
                GROUP BY COALESCE(series_name, title)
                ORDER BY watch_count DESC, last_watched DESC
                LIMIT ?
                """,
                (cutoff, limit),
            ) as cursor:
                async for row in cursor:
                    item = {
                        "app": row["app"],
                        "watch_count": row["watch_count"],
                        "total_time": row["total_time"] or 0,
                        "last_watched": row["last_watched"],
                    }
                    if row["title"]:
                        item["title"] = row["title"]
                    if row["series_name"]:
                        item["series_name"] = row["series_name"]
                    if row["media_type"]:
                        item["media_type"] = row["media_type"]
                    if row["genre"]:
                        item["genre"] = row["genre"]

                    items.append(item)

        return items

    async def set_content_preference(
        self,
        title: str | None = None,
        series_name: str | None = None,
        app: str | None = None,
        genre: str | None = None,
        rating: int | None = None,
        liked: bool | None = None,
    ) -> None:
        """Set user preference for content."""
        if not self._db:
            return

        if not title and not series_name:
            return

        now = datetime.utcnow().isoformat()

        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO content_preferences
                (title, series_name, app, genre, rating, liked, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(title, series_name, app)
                DO UPDATE SET
                    rating = COALESCE(?, rating),
                    liked = COALESCE(?, liked),
                    updated_at = ?
                """,
                (
                    title,
                    series_name,
                    app,
                    genre,
                    rating,
                    1 if liked else (0 if liked is False else None),
                    now,
                    rating,
                    1 if liked else (0 if liked is False else None),
                    now,
                ),
            )
            await self._db.commit()

    async def get_content_preferences(
        self, liked_only: bool = False
    ) -> list[dict[str, Any]]:
        """Get user content preferences."""
        if not self._db:
            return []

        prefs = []
        async with self._lock:
            query = "SELECT * FROM content_preferences"
            if liked_only:
                query += " WHERE liked = 1"
            query += " ORDER BY updated_at DESC"

            async with self._db.execute(query) as cursor:
                async for row in cursor:
                    pref = {}
                    if row["title"]:
                        pref["title"] = row["title"]
                    if row["series_name"]:
                        pref["series_name"] = row["series_name"]
                    if row["app"]:
                        pref["app"] = row["app"]
                    if row["genre"]:
                        pref["genre"] = row["genre"]
                    if row["rating"]:
                        pref["rating"] = row["rating"]
                    if row["liked"] is not None:
                        pref["liked"] = bool(row["liked"])
                    pref["updated_at"] = row["updated_at"]
                    prefs.append(pref)

        return prefs

    # Followed shows methods
    async def follow_show(
        self,
        series_name: str,
        app: str | None = None,
        tmdb_id: int | None = None,
        status: str | None = None,
        last_watched_season: int | None = None,
        last_watched_episode: int | None = None,
    ) -> None:
        """Follow a show for tracking new episodes."""
        if not self._db:
            return

        now = datetime.utcnow().isoformat()

        async with self._lock:
            await self._db.execute(
                """
                INSERT INTO followed_shows
                (series_name, tmdb_id, app, status, last_watched_season,
                 last_watched_episode, added_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(series_name) DO UPDATE SET
                    tmdb_id = COALESCE(?, tmdb_id),
                    app = COALESCE(?, app),
                    status = COALESCE(?, status),
                    last_watched_season = COALESCE(?, last_watched_season),
                    last_watched_episode = COALESCE(?, last_watched_episode),
                    updated_at = ?
                """,
                (
                    series_name,
                    tmdb_id,
                    app,
                    status,
                    last_watched_season,
                    last_watched_episode,
                    now,
                    now,
                    tmdb_id,
                    app,
                    status,
                    last_watched_season,
                    last_watched_episode,
                    now,
                ),
            )
            await self._db.commit()

    async def unfollow_show(self, series_name: str) -> bool:
        """Stop following a show."""
        if not self._db:
            return False

        async with self._lock:
            cursor = await self._db.execute(
                "DELETE FROM followed_shows WHERE series_name = ?",
                (series_name,),
            )
            await self._db.commit()
            return cursor.rowcount > 0

    async def get_followed_shows(self) -> list[dict[str, Any]]:
        """Get all followed shows."""
        if not self._db:
            return []

        shows = []
        async with self._lock:
            async with self._db.execute(
                "SELECT * FROM followed_shows ORDER BY updated_at DESC"
            ) as cursor:
                async for row in cursor:
                    show = {
                        "series_name": row["series_name"],
                        "added_at": row["added_at"],
                    }
                    if row["tmdb_id"]:
                        show["tmdb_id"] = row["tmdb_id"]
                    if row["app"]:
                        show["app"] = row["app"]
                    if row["status"]:
                        show["status"] = row["status"]
                    if row["last_watched_season"]:
                        show["last_watched_season"] = row["last_watched_season"]
                    if row["last_watched_episode"]:
                        show["last_watched_episode"] = row["last_watched_episode"]
                    shows.append(show)

        return shows

    async def update_show_progress(
        self, series_name: str, season: int, episode: int
    ) -> None:
        """Update where you left off on a show."""
        if not self._db:
            return

        now = datetime.utcnow().isoformat()

        async with self._lock:
            await self._db.execute(
                """
                UPDATE followed_shows
                SET last_watched_season = ?, last_watched_episode = ?, updated_at = ?
                WHERE series_name = ?
                """,
                (season, episode, now, series_name),
            )
            await self._db.commit()

    async def seed_favorites(
        self, shows: list[dict[str, Any]]
    ) -> int:
        """Seed initial favorites and followed shows.

        Args:
            shows: List of dicts with keys:
                - series_name (required): Show name
                - app (optional): Where to watch it
                - liked (optional): True to mark as liked

        Returns:
            Number of shows added
        """
        if not self._db:
            return 0

        count = 0
        for show in shows:
            series_name = show.get("series_name")
            if not series_name:
                continue

            app = show.get("app")
            liked = show.get("liked", True)

            # Add to followed shows
            await self.follow_show(series_name=series_name, app=app)

            # Also add to preferences if liked
            if liked:
                await self.set_content_preference(
                    series_name=series_name,
                    app=app,
                    liked=True,
                )

            count += 1

        return count

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

            # Clean up old audit logs
            cursor = await self._db.execute(
                "DELETE FROM audit_log WHERE timestamp < ?",
                (cutoff,),
            )
            audit_deleted = cursor.rowcount

            # Clean up completed/cancelled/failed scheduled actions
            cursor = await self._db.execute(
                """
                DELETE FROM scheduled_actions
                WHERE status IN ('completed', 'cancelled', 'failed')
                AND created_at < ?
                """,
                (cutoff,),
            )
            schedules_deleted = cursor.rowcount

            # Clean up viewing history (keep 90 days by default)
            viewing_cutoff = (datetime.utcnow() - timedelta(days=90)).isoformat()
            cursor = await self._db.execute(
                "DELETE FROM viewing_history WHERE started_at < ?",
                (viewing_cutoff,),
            )
            viewing_deleted = cursor.rowcount

            await self._db.commit()

            total = device_deleted + presence_deleted + audit_deleted + schedules_deleted + viewing_deleted
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
