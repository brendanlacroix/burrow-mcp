"""Roomba vacuum implementation for Burrow MCP.

Uses the roombapy library for local control via MQTT.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from config import DeviceConfig, SecretsConfig
from models.base import DeviceStatus, DeviceType
from models.vacuum import Vacuum, VacuumState
from utils.retry import CircuitBreaker, CircuitBreakerOpen, retry_async

logger = logging.getLogger(__name__)

# Circuit breaker for Roomba MQTT operations (shared across all Roomba devices)
_roomba_circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60.0,
    half_open_max_calls=2,
)


# Roomba phase to VacuumState mapping
PHASE_MAP = {
    "charge": VacuumState.DOCKED,
    "run": VacuumState.CLEANING,
    "stuck": VacuumState.STUCK,
    "stop": VacuumState.PAUSED,
    "pause": VacuumState.PAUSED,
    "hmUsrDock": VacuumState.RETURNING,
    "hmMidMsn": VacuumState.RETURNING,
    "hmPostMsn": VacuumState.RETURNING,
    "evac": VacuumState.DOCKED,  # Emptying bin
}


@dataclass
class RoombaVacuum(Vacuum):
    """Roomba vacuum implementation using roombapy library."""

    device_type: DeviceType = field(default=DeviceType.VACUUM, init=False)
    _ip: str | None = None
    _blid: str | None = None
    _password: str | None = None
    _robot: Any = field(default=None, repr=False)
    _connected: bool = False

    async def _run_with_retry(self, func: Any, *args: Any) -> Any:
        """Run a Roomba function with retry and circuit breaker.

        Uses retry for transient network errors and circuit breaker
        to prevent hammering an unresponsive device.
        """
        if _roomba_circuit_breaker.is_open:
            raise CircuitBreakerOpen("Roomba circuit breaker is open")

        try:
            result = await retry_async(
                asyncio.to_thread,
                func,
                *args,
                max_attempts=3,
                initial_delay=1.0,
                max_delay=10.0,
                retryable_exceptions=(OSError, TimeoutError, ConnectionError),
            )
            _roomba_circuit_breaker.record_success()
            return result
        except Exception:
            _roomba_circuit_breaker.record_failure()
            raise

    async def _ensure_connected(self) -> bool:
        """Ensure connection to Roomba."""
        if self._robot is None:
            logger.error(f"Roomba {self.id} not initialized")
            return False

        if not self._connected:
            try:
                # roombapy connect is synchronous, run in thread with retry
                await self._run_with_retry(self._robot.connect)
                self._connected = True
                logger.info(f"Connected to Roomba {self.id}")
            except CircuitBreakerOpen:
                logger.warning(f"Circuit breaker open for Roomba {self.id}")
                return False
            except Exception as e:
                logger.error(f"Failed to connect to Roomba {self.id}: {e}")
                return False

        return True

    async def refresh(self) -> None:
        """Fetch current state from Roomba."""
        if not await self._ensure_connected():
            self.status = DeviceStatus.OFFLINE
            return

        try:
            # Get master state from roombapy
            state = self._robot.master_state

            if state:
                # Extract reported state
                reported = state.get("state", {}).get("reported", {})

                # Get cleaning phase
                clean_mission = reported.get("cleanMissionStatus", {})
                phase = clean_mission.get("phase", "")

                self.vacuum_state = PHASE_MAP.get(phase, VacuumState.UNKNOWN)

                # Get battery
                bat_pct = reported.get("batPct")
                if bat_pct is not None:
                    self.battery_percent = bat_pct

                self.status = DeviceStatus.ONLINE
                logger.debug(
                    f"Refreshed Roomba {self.id}: state={self.vacuum_state.value}, "
                    f"battery={self.battery_percent}%"
                )
            else:
                self.status = DeviceStatus.OFFLINE

        except Exception as e:
            logger.error(f"Failed to refresh Roomba {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE

    async def start(self) -> None:
        """Start cleaning."""
        if not await self._ensure_connected():
            raise RuntimeError(f"Roomba {self.id} not connected")

        try:
            await self._run_with_retry(self._robot.send_command, "start")
            self.vacuum_state = VacuumState.CLEANING
            self.status = DeviceStatus.ONLINE
            logger.info(f"Started Roomba {self.id}")

        except CircuitBreakerOpen:
            logger.warning(f"Circuit breaker open for Roomba {self.id}")
            self.status = DeviceStatus.OFFLINE
            raise RuntimeError(f"Roomba {self.id} temporarily unavailable (circuit breaker open)")
        except Exception as e:
            logger.error(f"Failed to start Roomba {self.id}: {e}")
            raise

    async def stop(self) -> None:
        """Stop cleaning (pause)."""
        if not await self._ensure_connected():
            raise RuntimeError(f"Roomba {self.id} not connected")

        try:
            await self._run_with_retry(self._robot.send_command, "stop")
            self.vacuum_state = VacuumState.PAUSED
            self.status = DeviceStatus.ONLINE
            logger.info(f"Stopped Roomba {self.id}")

        except CircuitBreakerOpen:
            logger.warning(f"Circuit breaker open for Roomba {self.id}")
            self.status = DeviceStatus.OFFLINE
            raise RuntimeError(f"Roomba {self.id} temporarily unavailable (circuit breaker open)")
        except Exception as e:
            logger.error(f"Failed to stop Roomba {self.id}: {e}")
            raise

    async def dock(self) -> None:
        """Return to dock."""
        if not await self._ensure_connected():
            raise RuntimeError(f"Roomba {self.id} not connected")

        try:
            await self._run_with_retry(self._robot.send_command, "dock")
            self.vacuum_state = VacuumState.RETURNING
            self.status = DeviceStatus.ONLINE
            logger.info(f"Sending Roomba {self.id} to dock")

        except CircuitBreakerOpen:
            logger.warning(f"Circuit breaker open for Roomba {self.id}")
            self.status = DeviceStatus.OFFLINE
            raise RuntimeError(f"Roomba {self.id} temporarily unavailable (circuit breaker open)")
        except Exception as e:
            logger.error(f"Failed to dock Roomba {self.id}: {e}")
            raise

    async def pause(self) -> None:
        """Pause cleaning (alias for stop)."""
        await self.stop()

    async def resume(self) -> None:
        """Resume cleaning."""
        if not await self._ensure_connected():
            raise RuntimeError(f"Roomba {self.id} not connected")

        try:
            await self._run_with_retry(self._robot.send_command, "resume")
            self.vacuum_state = VacuumState.CLEANING
            self.status = DeviceStatus.ONLINE
            logger.info(f"Resumed Roomba {self.id}")

        except CircuitBreakerOpen:
            logger.warning(f"Circuit breaker open for Roomba {self.id}")
            self.status = DeviceStatus.OFFLINE
            raise RuntimeError(f"Roomba {self.id} temporarily unavailable (circuit breaker open)")
        except Exception as e:
            logger.error(f"Failed to resume Roomba {self.id}: {e}")
            raise

    async def disconnect(self) -> None:
        """Disconnect from Roomba."""
        if self._robot and self._connected:
            try:
                await asyncio.to_thread(self._robot.disconnect)
                self._connected = False
                logger.info(f"Disconnected from Roomba {self.id}")
            except Exception as e:
                logger.warning(f"Error disconnecting from Roomba {self.id}: {e}")

    async def reconnect(self) -> None:
        """Attempt to reconnect to Roomba."""
        # Reset circuit breaker to allow retry
        _roomba_circuit_breaker.reset()
        # Disconnect first
        self._connected = False
        await self.refresh()


async def create_roomba_vacuum(
    device_config: DeviceConfig, secrets: SecretsConfig
) -> RoombaVacuum:
    """Factory function to create a Roomba vacuum from config.

    Requires:
    - IP address of the Roomba
    - BLID (robot ID) - get using roombapy tools
    - Password - get using roombapy tools
    """
    try:
        from roombapy import Roomba
    except ImportError:
        logger.error("roombapy package not installed. Install with: pip install roombapy")
        return RoombaVacuum(
            id=device_config.id,
            name=device_config.name,
            room_id=device_config.room,
        )

    ip = device_config.config.get("ip")
    blid = secrets.roomba.get("blid") or device_config.config.get("blid")
    password = secrets.roomba.get("password") or device_config.config.get("password")

    vacuum = RoombaVacuum(
        id=device_config.id,
        name=device_config.name,
        room_id=device_config.room,
        _ip=ip,
        _blid=blid,
        _password=password,
    )

    if not ip:
        logger.warning(f"No IP address for Roomba {device_config.id}")
        return vacuum

    if not blid or not password:
        logger.warning(
            f"Roomba {device_config.id} missing blid/password. "
            "Use 'roombapy discover' to find credentials."
        )
        return vacuum

    try:
        # Create Roomba instance
        robot = Roomba(
            address=ip,
            blid=blid,
            password=password,
        )
        vacuum._robot = robot

        # Try to connect and get initial state
        try:
            await vacuum.refresh()
        except Exception as e:
            logger.warning(f"Initial refresh failed for Roomba {device_config.id}: {e}")

    except Exception as e:
        logger.error(f"Failed to initialize Roomba {device_config.id}: {e}")

    return vacuum


async def discover_roomba(timeout: float = 10.0) -> list[dict[str, Any]]:
    """Discover Roomba devices on the network.

    Note: This only finds devices, not credentials.
    Use roombapy's getpassword tool to get blid/password.

    Args:
        timeout: Discovery timeout in seconds

    Returns:
        List of discovered devices
    """
    try:
        from roombapy import RoombaDiscovery
    except ImportError:
        logger.error("roombapy package not installed")
        return []

    logger.info(f"Scanning for Roomba devices ({timeout}s)...")

    try:
        discovery = RoombaDiscovery()
        devices = await asyncio.to_thread(discovery.find, timeout=timeout)

        results = []
        for device in devices:
            results.append({
                "ip": device.ip,
                "hostname": device.hostname,
                "robot_name": getattr(device, "robot_name", None),
                "blid": getattr(device, "blid", None),
            })
            logger.info(f"Found Roomba: {device.ip}")

        return results

    except Exception as e:
        logger.error(f"Roomba discovery failed: {e}")
        return []
