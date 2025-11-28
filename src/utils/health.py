"""Health monitoring and automatic reconnection for devices."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from models.base import DeviceStatus

logger = logging.getLogger(__name__)


@dataclass
class DeviceHealth:
    """Health status for a device."""

    device_id: str
    last_successful_contact: datetime | None = None
    last_failed_contact: datetime | None = None
    consecutive_failures: int = 0
    total_failures: int = 0
    total_successes: int = 0
    is_healthy: bool = True

    def record_success(self) -> None:
        """Record a successful operation."""
        self.last_successful_contact = datetime.now()
        self.consecutive_failures = 0
        self.total_successes += 1
        self.is_healthy = True

    def record_failure(self) -> None:
        """Record a failed operation."""
        self.last_failed_contact = datetime.now()
        self.consecutive_failures += 1
        self.total_failures += 1
        if self.consecutive_failures >= 3:
            self.is_healthy = False

    @property
    def failure_rate(self) -> float:
        """Get the overall failure rate."""
        total = self.total_failures + self.total_successes
        if total == 0:
            return 0.0
        return self.total_failures / total

    @property
    def uptime_seconds(self) -> float | None:
        """Get seconds since last failure (None if never contacted)."""
        if self.last_successful_contact is None:
            return None
        if self.last_failed_contact is None:
            return (datetime.now() - self.last_successful_contact).total_seconds()
        if self.last_successful_contact > self.last_failed_contact:
            return (datetime.now() - self.last_successful_contact).total_seconds()
        return 0.0


class HealthMonitor:
    """Monitors device health and triggers reconnection when needed."""

    def __init__(
        self,
        check_interval: float = 60.0,
        unhealthy_threshold: int = 3,
        reconnect_delay: float = 30.0,
    ):
        """Initialize health monitor.

        Args:
            check_interval: Seconds between health checks
            unhealthy_threshold: Consecutive failures to mark unhealthy
            reconnect_delay: Seconds to wait before reconnection attempt
        """
        self.check_interval = check_interval
        self.unhealthy_threshold = unhealthy_threshold
        self.reconnect_delay = reconnect_delay

        self._device_health: dict[str, DeviceHealth] = {}
        self._check_functions: dict[str, Callable[[], Any]] = {}
        self._reconnect_functions: dict[str, Callable[[], Any]] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    def register_device(
        self,
        device_id: str,
        check_func: Callable[[], Any],
        reconnect_func: Callable[[], Any] | None = None,
    ) -> None:
        """Register a device for health monitoring.

        Args:
            device_id: Unique device identifier
            check_func: Async function that checks device health (should raise on failure)
            reconnect_func: Optional async function to attempt reconnection
        """
        self._device_health[device_id] = DeviceHealth(device_id=device_id)
        self._check_functions[device_id] = check_func
        if reconnect_func:
            self._reconnect_functions[device_id] = reconnect_func

    def unregister_device(self, device_id: str) -> None:
        """Unregister a device from monitoring."""
        self._device_health.pop(device_id, None)
        self._check_functions.pop(device_id, None)
        self._reconnect_functions.pop(device_id, None)

    def get_device_health(self, device_id: str) -> DeviceHealth | None:
        """Get health status for a device."""
        return self._device_health.get(device_id)

    def get_all_health(self) -> dict[str, DeviceHealth]:
        """Get health status for all devices."""
        return dict(self._device_health)

    def get_unhealthy_devices(self) -> list[str]:
        """Get list of unhealthy device IDs."""
        return [
            device_id
            for device_id, health in self._device_health.items()
            if not health.is_healthy
        ]

    async def check_device(self, device_id: str) -> bool:
        """Check a single device's health.

        Returns:
            True if healthy, False if unhealthy
        """
        check_func = self._check_functions.get(device_id)
        health = self._device_health.get(device_id)

        if not check_func or not health:
            return False

        try:
            await check_func()
            health.record_success()
            return True
        except Exception as e:
            health.record_failure()
            logger.warning(
                f"Health check failed for {device_id}: {e} "
                f"(consecutive failures: {health.consecutive_failures})"
            )

            # Attempt reconnection if available and threshold reached
            if (
                health.consecutive_failures >= self.unhealthy_threshold
                and device_id in self._reconnect_functions
            ):
                await self._attempt_reconnect(device_id)

            return False

    async def _attempt_reconnect(self, device_id: str) -> bool:
        """Attempt to reconnect a device.

        Returns:
            True if reconnection successful
        """
        reconnect_func = self._reconnect_functions.get(device_id)
        if not reconnect_func:
            return False

        logger.info(f"Attempting reconnection for {device_id}...")
        await asyncio.sleep(self.reconnect_delay)

        try:
            await reconnect_func()
            logger.info(f"Reconnection successful for {device_id}")
            health = self._device_health.get(device_id)
            if health:
                health.record_success()
            return True
        except Exception as e:
            logger.error(f"Reconnection failed for {device_id}: {e}")
            return False

    async def check_all(self, timeout: float = 30.0) -> dict[str, bool]:
        """Check health of all registered devices with timeout protection.

        Args:
            timeout: Maximum time to wait for all checks (default 30s)

        Returns:
            Dict mapping device_id to health status
        """
        results = {}
        tasks = []
        device_ids = list(self._check_functions.keys())

        for device_id in device_ids:
            tasks.append(self.check_device(device_id))

        try:
            async with asyncio.timeout(timeout):
                task_results = await asyncio.gather(*tasks, return_exceptions=True)
        except asyncio.TimeoutError:
            logger.error(f"check_all timed out after {timeout}s")
            # Mark all devices as unhealthy on timeout
            for device_id in device_ids:
                results[device_id] = False
                health = self._device_health.get(device_id)
                if health:
                    health.record_failure()
            return results

        for device_id, result in zip(device_ids, task_results):
            if isinstance(result, Exception):
                results[device_id] = False
            else:
                results[device_id] = result

        return results

    async def start(self) -> None:
        """Start the health monitoring loop."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Health monitor started")

    async def stop(self) -> None:
        """Stop the health monitoring loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Health monitor stopped")

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self.check_all()
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                await asyncio.sleep(self.check_interval)

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of all device health."""
        healthy_count = sum(1 for h in self._device_health.values() if h.is_healthy)
        total_count = len(self._device_health)

        return {
            "total_devices": total_count,
            "healthy_devices": healthy_count,
            "unhealthy_devices": total_count - healthy_count,
            "devices": {
                device_id: {
                    "is_healthy": health.is_healthy,
                    "consecutive_failures": health.consecutive_failures,
                    "failure_rate": round(health.failure_rate, 3),
                    "last_success": (
                        health.last_successful_contact.isoformat()
                        if health.last_successful_contact
                        else None
                    ),
                }
                for device_id, health in self._device_health.items()
            },
        }
