"""Cloud-based Roomba vacuum implementation for Burrow MCP.

Uses the irbt library for iRobot cloud API control.
This is for newer Roombas that use the "Roomba Home" app.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from config import DeviceConfig, SecretsConfig
from models.base import DeviceStatus, DeviceType
from models.vacuum import Vacuum, VacuumState

logger = logging.getLogger(__name__)


# iRobot cloud state to VacuumState mapping
CLOUD_STATE_MAP = {
    "charge": VacuumState.DOCKED,
    "run": VacuumState.CLEANING,
    "stuck": VacuumState.STUCK,
    "stop": VacuumState.PAUSED,
    "pause": VacuumState.PAUSED,
    "hmUsrDock": VacuumState.RETURNING,
    "hmMidMsn": VacuumState.RETURNING,
    "hmPostMsn": VacuumState.RETURNING,
    "evac": VacuumState.DOCKED,  # Emptying bin
    "Running": VacuumState.CLEANING,
    "Charging": VacuumState.DOCKED,
    "Stuck": VacuumState.STUCK,
    "Paused": VacuumState.PAUSED,
}


@dataclass
class RoombaCloudVacuum(Vacuum):
    """Roomba vacuum implementation using iRobot cloud API (irbt library)."""

    device_type: DeviceType = field(default=DeviceType.VACUUM, init=False)
    _username: str | None = None
    _password: str | None = None
    _robot_id: str | None = None
    _cloud: Any = field(default=None, repr=False)
    _robot: Any = field(default=None, repr=False)
    _connected: bool = False

    async def _ensure_connected(self) -> bool:
        """Ensure connection to iRobot cloud."""
        if self._cloud is None:
            logger.error(f"Roomba cloud {self.id} not initialized")
            return False

        if not self._connected:
            try:
                # irbt operations are synchronous, run in thread
                await asyncio.to_thread(self._robot.connect)
                self._connected = True
                logger.info(f"Connected to Roomba cloud {self.id}")
            except Exception as e:
                logger.error(f"Failed to connect to Roomba cloud {self.id}: {e}")
                return False

        return True

    async def refresh(self) -> None:
        """Fetch current state from iRobot cloud."""
        if not await self._ensure_connected():
            self.status = DeviceStatus.OFFLINE
            return

        try:
            # Get status via cloud API
            status = await asyncio.to_thread(self._robot.command.status)

            if status:
                # Parse the state from status response
                state_str = status.get("state", "")
                self.vacuum_state = CLOUD_STATE_MAP.get(state_str, VacuumState.UNKNOWN)

                # Get battery if available
                bat_pct = status.get("batPct")
                if bat_pct is not None:
                    self.battery_percent = bat_pct

                self.status = DeviceStatus.ONLINE
                logger.debug(
                    f"Refreshed Roomba cloud {self.id}: state={self.vacuum_state.value}, "
                    f"battery={self.battery_percent}%"
                )
            else:
                self.status = DeviceStatus.OFFLINE

        except Exception as e:
            logger.error(f"Failed to refresh Roomba cloud {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE

    async def start(self) -> None:
        """Start cleaning."""
        if not await self._ensure_connected():
            raise RuntimeError(f"Roomba cloud {self.id} not connected")

        try:
            await asyncio.to_thread(self._robot.command.start)
            self.vacuum_state = VacuumState.CLEANING
            self.status = DeviceStatus.ONLINE
            logger.info(f"Started Roomba cloud {self.id}")

        except Exception as e:
            logger.error(f"Failed to start Roomba cloud {self.id}: {e}")
            raise

    async def stop(self) -> None:
        """Stop cleaning (pause)."""
        if not await self._ensure_connected():
            raise RuntimeError(f"Roomba cloud {self.id} not connected")

        try:
            await asyncio.to_thread(self._robot.command.stop)
            self.vacuum_state = VacuumState.PAUSED
            self.status = DeviceStatus.ONLINE
            logger.info(f"Stopped Roomba cloud {self.id}")

        except Exception as e:
            logger.error(f"Failed to stop Roomba cloud {self.id}: {e}")
            raise

    async def dock(self) -> None:
        """Return to dock."""
        if not await self._ensure_connected():
            raise RuntimeError(f"Roomba cloud {self.id} not connected")

        try:
            await asyncio.to_thread(self._robot.command.dock)
            self.vacuum_state = VacuumState.RETURNING
            self.status = DeviceStatus.ONLINE
            logger.info(f"Sending Roomba cloud {self.id} to dock")

        except Exception as e:
            logger.error(f"Failed to dock Roomba cloud {self.id}: {e}")
            raise

    async def pause(self) -> None:
        """Pause cleaning."""
        if not await self._ensure_connected():
            raise RuntimeError(f"Roomba cloud {self.id} not connected")

        try:
            await asyncio.to_thread(self._robot.command.pause)
            self.vacuum_state = VacuumState.PAUSED
            self.status = DeviceStatus.ONLINE
            logger.info(f"Paused Roomba cloud {self.id}")

        except Exception as e:
            logger.error(f"Failed to pause Roomba cloud {self.id}: {e}")
            raise

    async def resume(self) -> None:
        """Resume cleaning."""
        if not await self._ensure_connected():
            raise RuntimeError(f"Roomba cloud {self.id} not connected")

        try:
            await asyncio.to_thread(self._robot.command.resume)
            self.vacuum_state = VacuumState.CLEANING
            self.status = DeviceStatus.ONLINE
            logger.info(f"Resumed Roomba cloud {self.id}")

        except Exception as e:
            logger.error(f"Failed to resume Roomba cloud {self.id}: {e}")
            raise

    async def find(self) -> None:
        """Make the robot beep to help locate it."""
        if not await self._ensure_connected():
            raise RuntimeError(f"Roomba cloud {self.id} not connected")

        try:
            await asyncio.to_thread(self._robot.command.find)
            logger.info(f"Finding Roomba cloud {self.id}")

        except Exception as e:
            logger.error(f"Failed to find Roomba cloud {self.id}: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from iRobot cloud."""
        if self._robot and self._connected:
            try:
                await asyncio.to_thread(self._robot.disconnect)
                self._connected = False
                logger.info(f"Disconnected from Roomba cloud {self.id}")
            except Exception as e:
                logger.warning(f"Error disconnecting from Roomba cloud {self.id}: {e}")

    def to_state_dict(self) -> dict[str, Any]:
        """Return current state as dict."""
        state = super().to_state_dict()
        state["control_method"] = "cloud"
        return state


async def create_roomba_cloud_vacuum(
    device_config: DeviceConfig, secrets: SecretsConfig
) -> RoombaCloudVacuum:
    """Factory function to create a cloud-controlled Roomba vacuum.

    Requires iRobot account credentials in secrets.yaml:
    roomba_cloud:
      username: "email@example.com"
      password: "password"

    The robot_id can be specified in device config, or will use the first
    robot found in the account.
    """
    try:
        from irbt import Cloud, Robot
    except ImportError:
        logger.error("irbt package not installed. Install with: pip install irbt")
        return RoombaCloudVacuum(
            id=device_config.id,
            name=device_config.name,
            room_id=device_config.room,
        )

    # Get cloud credentials
    username = secrets.roomba_cloud.get("username")
    password = secrets.roomba_cloud.get("password")

    # Robot ID can be in config or auto-discovered
    robot_id = device_config.config.get("robot_id")

    vacuum = RoombaCloudVacuum(
        id=device_config.id,
        name=device_config.name,
        room_id=device_config.room,
        _username=username,
        _password=password,
        _robot_id=robot_id,
    )

    if not username or not password:
        logger.warning(
            f"Roomba cloud {device_config.id} missing credentials. "
            "Add username/password to secrets.yaml under roomba_cloud."
        )
        return vacuum

    try:
        # Initialize cloud connection
        cloud = Cloud()
        await asyncio.to_thread(cloud.login, username, password)
        vacuum._cloud = cloud

        # Get robot - either by ID or first available
        if robot_id:
            robot = Robot(cloud=cloud, rid=robot_id)
        else:
            # Get list of robots and use the first one
            # or match by name if device_name is specified
            robots = await asyncio.to_thread(cloud.robots)
            if not robots:
                logger.warning(f"No robots found in iRobot account for {device_config.id}")
                return vacuum

            # Try to match by name or index
            robot_name = device_config.config.get("robot_name")
            robot_index = device_config.config.get("robot_index", 0)

            if robot_name:
                # Find robot by name
                matched = None
                for r in robots:
                    if r.get("name", "").lower() == robot_name.lower():
                        matched = r
                        break
                if matched:
                    robot = Robot(cloud=cloud, rid=matched.get("rid"))
                    vacuum._robot_id = matched.get("rid")
                else:
                    logger.warning(
                        f"Robot named '{robot_name}' not found. "
                        f"Available: {[r.get('name') for r in robots]}"
                    )
                    # Fall back to first robot
                    robot = Robot(cloud=cloud, rid=robots[0].get("rid"))
                    vacuum._robot_id = robots[0].get("rid")
            else:
                # Use robot by index
                if robot_index < len(robots):
                    robot = Robot(cloud=cloud, rid=robots[robot_index].get("rid"))
                    vacuum._robot_id = robots[robot_index].get("rid")
                else:
                    logger.warning(
                        f"Robot index {robot_index} out of range. Using first robot."
                    )
                    robot = Robot(cloud=cloud, rid=robots[0].get("rid"))
                    vacuum._robot_id = robots[0].get("rid")

        vacuum._robot = robot

        # Try to get initial state
        try:
            await vacuum.refresh()
        except Exception as e:
            logger.warning(f"Initial refresh failed for Roomba cloud {device_config.id}: {e}")

        logger.info(f"Initialized Roomba cloud {device_config.id} (robot_id: {vacuum._robot_id})")

    except Exception as e:
        logger.error(f"Failed to initialize Roomba cloud {device_config.id}: {e}")

    return vacuum


async def list_cloud_robots(secrets: SecretsConfig) -> list[dict[str, Any]]:
    """List all robots in the iRobot cloud account.

    Useful for discovering robot IDs and names.

    Args:
        secrets: Secrets config with roomba_cloud credentials

    Returns:
        List of robot info dicts with 'rid', 'name', etc.
    """
    try:
        from irbt import Cloud
    except ImportError:
        logger.error("irbt package not installed")
        return []

    username = secrets.roomba_cloud.get("username")
    password = secrets.roomba_cloud.get("password")

    if not username or not password:
        logger.error("Missing roomba_cloud credentials in secrets")
        return []

    try:
        cloud = Cloud()
        await asyncio.to_thread(cloud.login, username, password)
        robots = await asyncio.to_thread(cloud.robots)

        results = []
        for robot in robots:
            results.append({
                "robot_id": robot.get("rid"),
                "name": robot.get("name"),
                "sku": robot.get("sku"),
                "software_ver": robot.get("softwareVer"),
            })
            logger.info(f"Found cloud robot: {robot.get('name')} ({robot.get('rid')})")

        return results

    except Exception as e:
        logger.error(f"Failed to list cloud robots: {e}")
        return []
