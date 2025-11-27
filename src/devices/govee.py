"""Govee light implementation for Burrow MCP.

Uses the Govee Cloud API for device control.
API docs: https://govee-public.s3.amazonaws.com/developer-docs/GoveeDeveloperAPIReference.pdf
"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

from config import DeviceConfig, SecretsConfig
from models.base import DeviceStatus, DeviceType
from models.light import Light
from utils.errors import RateLimitedError
from utils.rate_limit import get_service_rate_limiter
from utils.retry import CircuitBreaker, CircuitBreakerOpen, with_circuit_breaker, with_retry

logger = logging.getLogger(__name__)

GOVEE_API_BASE = "https://developer-api.govee.com/v1"

# Circuit breaker for Govee API (shared across all Govee devices)
_govee_circuit_breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60.0,
    half_open_max_calls=2,
)


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convert hex color to RGB tuple."""
    hex_color = hex_color.lstrip("#")
    return (
        int(hex_color[0:2], 16),
        int(hex_color[2:4], 16),
        int(hex_color[4:6], 16),
    )


def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Convert RGB to hex color."""
    return f"#{r:02x}{g:02x}{b:02x}"


@dataclass
class GoveeLight(Light):
    """Govee light implementation using cloud API."""

    device_type: DeviceType = field(default=DeviceType.LIGHT, init=False)
    _api_key: str | None = None
    _device_id: str | None = None
    _model: str | None = None
    _client: httpx.AsyncClient | None = field(default=None, repr=False)
    _rate_limiter: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize rate limiter reference."""
        super().__post_init__()
        self._rate_limiter = get_service_rate_limiter()

    def _get_headers(self) -> dict[str, str]:
        """Get API headers."""
        return {
            "Govee-API-Key": self._api_key or "",
            "Content-Type": "application/json",
        }

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client exists."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def _rate_limited_request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
    ) -> dict[str, Any] | None:
        """Make rate-limited API request to Govee."""
        # Acquire rate limit token before making request
        await self._rate_limiter.acquire("govee")
        return await self._api_request(method, endpoint, json_data)

    @with_retry(
        max_attempts=3,
        initial_delay=1.0,
        max_delay=10.0,
        retryable_exceptions=(httpx.TimeoutException, httpx.ConnectError, ConnectionError),
    )
    @with_circuit_breaker(_govee_circuit_breaker)
    async def _api_request(
        self,
        method: str,
        endpoint: str,
        json_data: dict | None = None,
    ) -> dict[str, Any] | None:
        """Make API request to Govee with retry and circuit breaker."""
        if not self._api_key:
            logger.error(f"No API key for Govee device {self.id}")
            return None

        client = await self._ensure_client()
        url = f"{GOVEE_API_BASE}{endpoint}"

        try:
            if method == "GET":
                response = await client.get(url, headers=self._get_headers())
            elif method == "PUT":
                response = await client.put(url, headers=self._get_headers(), json=json_data)
            else:
                logger.error(f"Unknown method: {method}")
                return None

            # Handle rate limiting
            if response.status_code == 429:
                retry_after = float(response.headers.get("Retry-After", "30"))
                logger.warning(f"Rate limited by Govee API, retry after {retry_after}s")
                raise RateLimitedError("govee", retry_after=retry_after)

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"Govee API error for {self.id}: {e.response.status_code}")
            # Re-raise for circuit breaker to track
            raise
        except httpx.RequestError as e:
            logger.error(f"Govee request error for {self.id}: {e}")
            raise

    async def refresh(self) -> None:
        """Fetch current state from Govee cloud."""
        if not self._api_key or not self._device_id:
            self.status = DeviceStatus.OFFLINE
            return

        try:
            result = await self._rate_limited_request(
                "GET",
                f"/devices/state?device={self._device_id}&model={self._model}",
            )

            if not result or "data" not in result:
                self.status = DeviceStatus.OFFLINE
                return

            properties = result["data"].get("properties", [])
            for prop in properties:
                if "powerState" in prop:
                    self.is_on = prop["powerState"] == "on"
                elif "brightness" in prop:
                    self.brightness = prop["brightness"]
                elif "color" in prop:
                    color = prop["color"]
                    self.color = rgb_to_hex(color["r"], color["g"], color["b"])
                elif "colorTem" in prop:
                    self.color_temp = prop["colorTem"]

            self.status = DeviceStatus.ONLINE
            logger.debug(f"Refreshed Govee {self.id}: on={self.is_on}, brightness={self.brightness}")

        except CircuitBreakerOpen:
            logger.warning(f"Circuit breaker open for Govee {self.id}")
            self.status = DeviceStatus.OFFLINE
        except RateLimitedError as e:
            logger.warning(f"Rate limited refreshing Govee {self.id}: {e}")
            # Don't mark offline for rate limiting - it's a temporary issue
        except Exception as e:
            logger.error(f"Failed to refresh Govee {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE

    async def _send_command(self, cmd_name: str, cmd_value: Any) -> bool:
        """Send a command to the Govee device."""
        if not self._api_key or not self._device_id:
            raise RuntimeError(f"Govee device {self.id} not configured")

        try:
            result = await self._rate_limited_request(
                "PUT",
                "/devices/control",
                json_data={
                    "device": self._device_id,
                    "model": self._model,
                    "cmd": {
                        "name": cmd_name,
                        "value": cmd_value,
                    },
                },
            )

            if result and result.get("code") == 200:
                self.status = DeviceStatus.ONLINE
                return True
            else:
                logger.error(f"Govee command failed for {self.id}: {result}")
                return False

        except CircuitBreakerOpen:
            logger.warning(f"Circuit breaker open for Govee {self.id}")
            raise RuntimeError(f"Govee API temporarily unavailable (circuit breaker open)")
        except RateLimitedError as e:
            logger.warning(f"Rate limited sending command to Govee {self.id}: {e}")
            raise RuntimeError(f"Rate limited by Govee API. Try again in {e.retry_after}s")

    async def set_power(self, on: bool) -> None:
        """Turn the light on or off."""
        success = await self._send_command("turn", "on" if on else "off")
        if success:
            self.is_on = on

    async def set_brightness(self, brightness: int) -> None:
        """Set brightness (0-100)."""
        brightness = max(0, min(100, brightness))
        success = await self._send_command("brightness", brightness)
        if success:
            self.brightness = brightness
            if brightness > 0 and not self.is_on:
                await self.set_power(True)

    async def set_color(self, color: str) -> None:
        """Set color using hex code."""
        if not self.supports_color:
            raise ValueError(f"Govee device {self.id} does not support color")

        r, g, b = hex_to_rgb(color)
        success = await self._send_command("color", {"r": r, "g": g, "b": b})
        if success:
            self.color = color
            if not self.is_on:
                await self.set_power(True)

    async def set_color_temp(self, kelvin: int) -> None:
        """Set color temperature in Kelvin."""
        kelvin = max(2000, min(9000, kelvin))
        success = await self._send_command("colorTem", kelvin)
        if success:
            self.color_temp = kelvin
            self.color = None
            if not self.is_on:
                await self.set_power(True)

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def reconnect(self) -> None:
        """Attempt to reconnect by refreshing state."""
        # Close existing client and create new one
        await self.close()
        await self.refresh()


async def create_govee_light(device_config: DeviceConfig, secrets: SecretsConfig) -> GoveeLight:
    """Factory function to create a Govee light from config."""
    api_key = secrets.govee.get("api_key")
    if not api_key:
        logger.warning(f"No Govee API key found for {device_config.id}")

    device_id = device_config.config.get("device_id")
    model = device_config.config.get("model")

    if not device_id:
        logger.warning(f"No device_id specified for Govee device {device_config.id}")

    if not model:
        logger.warning(f"No model specified for Govee device {device_config.id}")

    light = GoveeLight(
        id=device_config.id,
        name=device_config.name,
        room_id=device_config.room,
        _api_key=api_key,
        _device_id=device_id,
        _model=model,
    )

    # Try initial refresh
    if api_key and device_id and model:
        try:
            await light.refresh()
        except Exception as e:
            logger.warning(f"Initial refresh failed for Govee {device_config.id}: {e}")

    return light


async def discover_govee_devices(api_key: str) -> list[dict[str, Any]]:
    """Discover Govee devices using the API.

    Args:
        api_key: Govee API key

    Returns:
        List of device info dicts with keys: device, model, deviceName, controllable, supportCmds
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{GOVEE_API_BASE}/devices",
                headers={
                    "Govee-API-Key": api_key,
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

            if data.get("code") == 200 and "data" in data:
                devices = data["data"].get("devices", [])
                logger.info(f"Discovered {len(devices)} Govee device(s)")
                return devices
            else:
                logger.error(f"Govee API error: {data}")
                return []

        except Exception as e:
            logger.error(f"Failed to discover Govee devices: {e}")
            return []
