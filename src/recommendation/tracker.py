"""Background viewing tracker for media devices.

This runs independently to track what's playing on AppleTVs (or other media devices),
building viewing history even when you're using the physical remote or phone app.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from devices.manager import DeviceManager
from models.media_device import MediaDevice, PlaybackState
from persistence import StateStore

logger = logging.getLogger(__name__)

# How often to check what's playing (seconds)
DEFAULT_POLL_INTERVAL = 30

# Minimum time to consider something "watched" (seconds)
MIN_WATCH_DURATION = 60


class ViewingTracker:
    """Background service that tracks viewing on media devices.

    Polls media devices periodically to see what's playing and logs
    viewing sessions. This captures viewing regardless of how the
    TV is being controlled (MCP, remote, phone app, etc.).
    """

    def __init__(
        self,
        device_manager: DeviceManager,
        store: StateStore,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ):
        self.device_manager = device_manager
        self.store = store
        self.poll_interval = poll_interval

        # Track active viewing sessions
        # {device_id: {"session_id": int, "content_hash": str, "started_at": datetime}}
        self._active_sessions: dict[str, dict[str, Any]] = {}

        # Background task
        self._task: asyncio.Task | None = None
        self._running = False

    def _get_content_hash(self, device: MediaDevice) -> str | None:
        """Generate a hash of current content for change detection."""
        if not device.now_playing:
            return None

        np = device.now_playing
        # Include app, title, series, season, episode for uniqueness
        return f"{np.app}|{np.title}|{np.series_name}|{np.season}|{np.episode}"

    async def _check_device(self, device: MediaDevice) -> None:
        """Check a single device and update viewing history."""
        try:
            # Refresh device state
            await device.refresh()

            device_id = device.id
            content_hash = self._get_content_hash(device)
            active_session = self._active_sessions.get(device_id)

            # Case 1: Nothing playing now
            if device.playback_state in (PlaybackState.IDLE, PlaybackState.STOPPED) or not device.now_playing:
                if active_session:
                    # End the active session
                    await self._end_session(device_id, active_session)
                return

            # Case 2: Something is playing
            if device.playback_state == PlaybackState.PLAYING:
                if active_session:
                    # Check if content changed
                    if active_session["content_hash"] != content_hash:
                        # End old session, start new one
                        await self._end_session(device_id, active_session)
                        await self._start_session(device, content_hash)
                    # else: same content, session continues
                else:
                    # No active session, start one
                    await self._start_session(device, content_hash)

            # Case 3: Paused - keep session alive but don't log yet
            elif device.playback_state == PlaybackState.PAUSED:
                # Session stays active, we'll update when resumed or ended
                pass

        except Exception as e:
            logger.warning(f"Error checking device {device.id}: {e}")

    async def _start_session(
        self, device: MediaDevice, content_hash: str | None
    ) -> None:
        """Start a new viewing session."""
        if not device.now_playing:
            return

        np = device.now_playing

        try:
            session_id = await self.store.record_viewing_session(
                device_id=device.id,
                app=np.app or "Unknown",
                title=np.title,
                series_name=np.series_name,
                season=np.season,
                episode=np.episode,
                media_type=np.media_type,
                genre=np.genre,
                duration=np.duration,
            )

            self._active_sessions[device.id] = {
                "session_id": session_id,
                "content_hash": content_hash,
                "started_at": datetime.utcnow(),
                "last_position": np.position or 0,
            }

            logger.debug(
                f"Started viewing session {session_id} on {device.id}: "
                f"{np.series_name or np.title} on {np.app}"
            )

        except Exception as e:
            logger.error(f"Failed to start viewing session: {e}")

    async def _end_session(
        self, device_id: str, session: dict[str, Any]
    ) -> None:
        """End an active viewing session."""
        session_id = session["session_id"]
        started_at = session["started_at"]
        elapsed = (datetime.utcnow() - started_at).total_seconds()

        # Only record if watched for minimum duration
        if elapsed < MIN_WATCH_DURATION:
            logger.debug(
                f"Session {session_id} too short ({elapsed:.0f}s), not recording"
            )
            del self._active_sessions[device_id]
            return

        try:
            # Estimate if completed (watched > 90% of duration)
            # This is a rough heuristic since we don't always have duration
            completed = False

            await self.store.update_viewing_session(
                session_id,
                watched_duration=int(elapsed),
                completed=completed,
            )

            logger.debug(
                f"Ended viewing session {session_id} on {device_id}: "
                f"{elapsed:.0f}s watched"
            )

        except Exception as e:
            logger.error(f"Failed to end viewing session: {e}")

        finally:
            del self._active_sessions[device_id]

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        logger.info(
            f"Viewing tracker started (polling every {self.poll_interval}s)"
        )

        while self._running:
            try:
                # Get all media devices
                media_devices = [
                    d for d in self.device_manager.get_all_devices()
                    if isinstance(d, MediaDevice)
                ]

                # Check each device
                for device in media_devices:
                    await self._check_device(device)

            except Exception as e:
                logger.error(f"Error in viewing tracker poll loop: {e}")

            # Wait for next poll
            await asyncio.sleep(self.poll_interval)

        # Clean up any active sessions when stopping
        for device_id, session in list(self._active_sessions.items()):
            await self._end_session(device_id, session)

        logger.info("Viewing tracker stopped")

    async def start(self) -> None:
        """Start the background tracker."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Viewing tracker starting...")

    async def stop(self) -> None:
        """Stop the background tracker."""
        if not self._running:
            return

        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def get_active_sessions(self) -> dict[str, dict[str, Any]]:
        """Get currently active viewing sessions (for debugging)."""
        return {
            device_id: {
                "session_id": s["session_id"],
                "content_hash": s["content_hash"],
                "duration": (datetime.utcnow() - s["started_at"]).total_seconds(),
            }
            for device_id, s in self._active_sessions.items()
        }


# Global tracker instance
_tracker: ViewingTracker | None = None


async def start_viewing_tracker(
    device_manager: DeviceManager,
    store: StateStore,
    poll_interval: int = DEFAULT_POLL_INTERVAL,
) -> ViewingTracker:
    """Start the global viewing tracker."""
    global _tracker

    if _tracker is None:
        _tracker = ViewingTracker(device_manager, store, poll_interval)
        await _tracker.start()

    return _tracker


async def stop_viewing_tracker() -> None:
    """Stop the global viewing tracker."""
    global _tracker

    if _tracker:
        await _tracker.stop()
        _tracker = None
