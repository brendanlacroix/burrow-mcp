"""MCP handlers for media device control."""

import asyncio
import logging
from typing import Any

from devices.manager import DeviceManager
from models import DeviceStatus
from models.media_device import MediaDevice
from mcp_server.handlers.audit_context import log_device_action
from mcp_server.handlers.schedule_context import add_schedule_context
from persistence import StateStore
from utils.errors import (
    DEFAULT_DEVICE_TIMEOUT,
    DeviceTimeoutError,
    ErrorCategory,
    ToolError,
    classify_exception,
    execute_with_timeout,
    get_recovery_suggestion,
)

logger = logging.getLogger(__name__)


class MediaHandlers:
    """Handlers for media device control tools."""

    def __init__(self, device_manager: DeviceManager, store: StateStore | None = None):
        self.device_manager = device_manager
        self.store = store
        self._current_sessions: dict[str, int] = {}  # device_id -> session_id

    def _get_media_device(self, device_id: str) -> MediaDevice | None:
        """Get a media device by ID."""
        device = self.device_manager.get_device(device_id)
        if device and isinstance(device, MediaDevice):
            return device
        return None

    def _check_device_online(
        self, device: MediaDevice, device_id: str
    ) -> ToolError | None:
        """Check if device is online."""
        if device.status == DeviceStatus.OFFLINE:
            return ToolError(
                category=ErrorCategory.DEVICE_OFFLINE,
                message=f"Media device {device_id} is offline",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.DEVICE_OFFLINE),
            )
        return None

    async def _track_viewing(self, device: MediaDevice) -> None:
        """Track viewing session when content changes."""
        if not self.store or not device.now_playing:
            return

        np = device.now_playing
        content_key = f"{np.app}:{np.title}:{np.series_name}:{np.season}:{np.episode}"

        # Check if this is new content
        current_session = self._current_sessions.get(device.id)

        if current_session:
            # End previous session
            await self.store.update_viewing_session(
                current_session,
                watched_duration=np.position,
                completed=False,
            )

        # Start new session
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
        self._current_sessions[device.id] = session_id

    async def get_now_playing(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get what's currently playing on a media device."""
        device_id = args["device_id"]

        device = self._get_media_device(device_id)
        if device is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Media device {device_id} not found",
                device_id=device_id,
                recovery="Use list_devices with device_type='media' to see available media devices",
            ).to_dict()

        try:
            # Refresh to get latest state
            await execute_with_timeout(
                device.refresh(),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="refresh",
            )

            # Track viewing
            await self._track_viewing(device)

            state = device.to_state_dict()
            state["device_id"] = device_id
            state["device_name"] = device.name
            state["status"] = device.status.value

            return state

        except (DeviceTimeoutError, asyncio.TimeoutError):
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Timeout getting state from {device_id}",
                device_id=device_id,
                recovery=get_recovery_suggestion(ErrorCategory.TIMEOUT),
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to get now playing from {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def media_play(self, args: dict[str, Any]) -> dict[str, Any]:
        """Resume or start playback."""
        device_id = args["device_id"]

        device = self._get_media_device(device_id)
        if device is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Media device {device_id} not found",
                device_id=device_id,
            ).to_dict()

        if error := self._check_device_online(device, device_id):
            return error.to_dict()

        try:
            previous_state = device.to_state_dict()

            await execute_with_timeout(
                device.play(),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="play",
            )

            await log_device_action(
                device_id=device_id,
                action="media_play",
                previous_state=previous_state,
                new_state=device.to_state_dict(),
            )

            response = {
                "success": True,
                "device_id": device_id,
                "playback_state": device.playback_state.value,
            }
            return await add_schedule_context(response, device_id)

        except (DeviceTimeoutError, asyncio.TimeoutError):
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Timeout sending play to {device_id}",
                device_id=device_id,
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to play on {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def media_pause(self, args: dict[str, Any]) -> dict[str, Any]:
        """Pause playback."""
        device_id = args["device_id"]

        device = self._get_media_device(device_id)
        if device is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Media device {device_id} not found",
                device_id=device_id,
            ).to_dict()

        if error := self._check_device_online(device, device_id):
            return error.to_dict()

        try:
            previous_state = device.to_state_dict()

            await execute_with_timeout(
                device.pause(),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="pause",
            )

            await log_device_action(
                device_id=device_id,
                action="media_pause",
                previous_state=previous_state,
                new_state=device.to_state_dict(),
            )

            response = {
                "success": True,
                "device_id": device_id,
                "playback_state": device.playback_state.value,
            }
            return await add_schedule_context(response, device_id)

        except (DeviceTimeoutError, asyncio.TimeoutError):
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Timeout sending pause to {device_id}",
                device_id=device_id,
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to pause {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def media_stop(self, args: dict[str, Any]) -> dict[str, Any]:
        """Stop playback."""
        device_id = args["device_id"]

        device = self._get_media_device(device_id)
        if device is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Media device {device_id} not found",
                device_id=device_id,
            ).to_dict()

        if error := self._check_device_online(device, device_id):
            return error.to_dict()

        try:
            previous_state = device.to_state_dict()

            # End viewing session before stopping
            if device.id in self._current_sessions and self.store:
                session_id = self._current_sessions.pop(device.id)
                position = device.now_playing.position if device.now_playing else None
                await self.store.update_viewing_session(
                    session_id,
                    watched_duration=position,
                    completed=False,
                )

            await execute_with_timeout(
                device.stop(),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="stop",
            )

            await log_device_action(
                device_id=device_id,
                action="media_stop",
                previous_state=previous_state,
                new_state=device.to_state_dict(),
            )

            response = {
                "success": True,
                "device_id": device_id,
                "playback_state": device.playback_state.value,
            }
            return await add_schedule_context(response, device_id)

        except (DeviceTimeoutError, asyncio.TimeoutError):
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Timeout sending stop to {device_id}",
                device_id=device_id,
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to stop {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def media_skip_forward(self, args: dict[str, Any]) -> dict[str, Any]:
        """Skip to next track/episode."""
        device_id = args["device_id"]

        device = self._get_media_device(device_id)
        if device is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Media device {device_id} not found",
                device_id=device_id,
            ).to_dict()

        if error := self._check_device_online(device, device_id):
            return error.to_dict()

        try:
            previous_state = device.to_state_dict()

            await execute_with_timeout(
                device.skip_forward(),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="skip_forward",
            )

            # Refresh to get new content info
            await device.refresh()

            await log_device_action(
                device_id=device_id,
                action="media_skip_forward",
                previous_state=previous_state,
                new_state=device.to_state_dict(),
            )

            # Track new content
            await self._track_viewing(device)

            response = {
                "success": True,
                "device_id": device_id,
            }
            if device.now_playing:
                response["now_playing"] = device.now_playing.to_dict()

            return response

        except (DeviceTimeoutError, asyncio.TimeoutError):
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Timeout skipping forward on {device_id}",
                device_id=device_id,
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to skip forward on {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def media_skip_backward(self, args: dict[str, Any]) -> dict[str, Any]:
        """Skip to previous track/episode."""
        device_id = args["device_id"]

        device = self._get_media_device(device_id)
        if device is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Media device {device_id} not found",
                device_id=device_id,
            ).to_dict()

        if error := self._check_device_online(device, device_id):
            return error.to_dict()

        try:
            previous_state = device.to_state_dict()

            await execute_with_timeout(
                device.skip_backward(),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="skip_backward",
            )

            # Refresh to get new content info
            await device.refresh()

            await log_device_action(
                device_id=device_id,
                action="media_skip_backward",
                previous_state=previous_state,
                new_state=device.to_state_dict(),
            )

            response = {
                "success": True,
                "device_id": device_id,
            }
            if device.now_playing:
                response["now_playing"] = device.now_playing.to_dict()

            return response

        except (DeviceTimeoutError, asyncio.TimeoutError):
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Timeout skipping backward on {device_id}",
                device_id=device_id,
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to skip backward on {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def launch_app(self, args: dict[str, Any]) -> dict[str, Any]:
        """Launch a streaming app."""
        device_id = args["device_id"]
        app = args["app"]

        device = self._get_media_device(device_id)
        if device is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Media device {device_id} not found",
                device_id=device_id,
            ).to_dict()

        if error := self._check_device_online(device, device_id):
            return error.to_dict()

        try:
            previous_state = device.to_state_dict()

            await execute_with_timeout(
                device.launch_app(app),
                timeout=DEFAULT_DEVICE_TIMEOUT + 5,  # Apps can take longer to launch
                device_id=device_id,
                operation="launch_app",
            )

            await log_device_action(
                device_id=device_id,
                action="launch_app",
                previous_state=previous_state,
                new_state=device.to_state_dict(),
                metadata={"app": app},
            )

            response = {
                "success": True,
                "device_id": device_id,
                "app_launched": device.current_app,
            }
            return response

        except ValueError as e:
            # App not found
            return ToolError(
                category=ErrorCategory.INVALID_INPUT,
                message=str(e),
                device_id=device_id,
                recovery="Use list_apps to see available apps",
            ).to_dict()
        except (DeviceTimeoutError, asyncio.TimeoutError):
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Timeout launching {app} on {device_id}",
                device_id=device_id,
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to launch {app} on {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()

    async def list_apps(self, args: dict[str, Any]) -> dict[str, Any]:
        """List installed apps on a media device."""
        device_id = args["device_id"]

        device = self._get_media_device(device_id)
        if device is None:
            return ToolError(
                category=ErrorCategory.DEVICE_NOT_FOUND,
                message=f"Media device {device_id} not found",
                device_id=device_id,
            ).to_dict()

        if error := self._check_device_online(device, device_id):
            return error.to_dict()

        try:
            apps = await execute_with_timeout(
                device.get_app_list(),
                timeout=DEFAULT_DEVICE_TIMEOUT,
                device_id=device_id,
                operation="get_app_list",
            )

            return {
                "device_id": device_id,
                "apps": apps,
                "current_app": device.current_app,
            }

        except (DeviceTimeoutError, asyncio.TimeoutError):
            return ToolError(
                category=ErrorCategory.TIMEOUT,
                message=f"Timeout getting apps from {device_id}",
                device_id=device_id,
            ).to_dict()
        except Exception as e:
            logger.error(f"Failed to list apps on {device_id}: {e}")
            error = classify_exception(e, device_id)
            return error.to_dict()
