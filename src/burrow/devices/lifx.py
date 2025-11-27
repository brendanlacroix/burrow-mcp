"""LIFX light implementation for Burrow MCP."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from burrow.config import DeviceConfig, SecretsConfig
from burrow.models.device import DeviceStatus, DeviceType, Light

logger = logging.getLogger(__name__)


def hex_to_hsbk(hex_color: str) -> tuple[int, int, int, int]:
    """Convert hex color to LIFX HSBK format.

    Args:
        hex_color: Color in hex format (e.g., "#FF0000")

    Returns:
        Tuple of (hue, saturation, brightness, kelvin) in LIFX scale
    """
    # Remove # prefix if present
    hex_color = hex_color.lstrip("#")

    # Parse RGB
    r = int(hex_color[0:2], 16) / 255.0
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0

    # Convert RGB to HSV
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    diff = max_c - min_c

    # Hue
    if diff == 0:
        h = 0
    elif max_c == r:
        h = (60 * ((g - b) / diff) + 360) % 360
    elif max_c == g:
        h = (60 * ((b - r) / diff) + 120) % 360
    else:
        h = (60 * ((r - g) / diff) + 240) % 360

    # Saturation
    s = 0 if max_c == 0 else (diff / max_c)

    # Value (brightness)
    v = max_c

    # Convert to LIFX scale (16-bit values)
    hue = int((h / 360.0) * 65535)
    saturation = int(s * 65535)
    brightness = int(v * 65535)
    kelvin = 3500  # Default kelvin for color mode

    return hue, saturation, brightness, kelvin


def hsbk_to_hex(hue: int, saturation: int, brightness: int) -> str:
    """Convert LIFX HSBK to hex color.

    Args:
        hue: LIFX hue (0-65535)
        saturation: LIFX saturation (0-65535)
        brightness: LIFX brightness (0-65535)

    Returns:
        Hex color string
    """
    # Convert from LIFX scale to 0-1 range
    h = (hue / 65535.0) * 360
    s = saturation / 65535.0
    v = brightness / 65535.0

    # Convert HSV to RGB
    c = v * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = v - c

    if h < 60:
        r, g, b = c, x, 0
    elif h < 120:
        r, g, b = x, c, 0
    elif h < 180:
        r, g, b = 0, c, x
    elif h < 240:
        r, g, b = 0, x, c
    elif h < 300:
        r, g, b = x, 0, c
    else:
        r, g, b = c, 0, x

    r = int((r + m) * 255)
    g = int((g + m) * 255)
    b = int((b + m) * 255)

    return f"#{r:02x}{g:02x}{b:02x}"


@dataclass
class LifxLight(Light):
    """LIFX light implementation."""

    device_type: DeviceType = field(default=DeviceType.LIGHT, init=False)
    _lifx_device: Any = field(default=None, repr=False)
    _mac: str | None = None
    _ip: str | None = None

    async def _run_sync(self, func: Any, *args: Any) -> Any:
        """Run a synchronous LIFX function in a thread."""
        return await asyncio.to_thread(func, *args)

    async def refresh(self) -> None:
        """Fetch current state from the LIFX bulb."""
        if self._lifx_device is None:
            self.status = DeviceStatus.OFFLINE
            return

        try:
            # Get power state
            power = await self._run_sync(self._lifx_device.get_power)
            self.is_on = power > 0

            # Get color (HSBK)
            color = await self._run_sync(self._lifx_device.get_color)
            if color:
                hue, saturation, brightness, kelvin = color
                # Convert brightness from 0-65535 to 0-100
                self.brightness = int((brightness / 65535.0) * 100)
                self.color_temp = kelvin

                # Only set color if saturation is significant
                if saturation > 1000:  # Threshold for "has color"
                    self.color = hsbk_to_hex(hue, saturation, brightness)
                else:
                    self.color = None

            self.status = DeviceStatus.ONLINE
        except Exception as e:
            logger.error(f"Failed to refresh LIFX {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE

    async def set_power(self, on: bool) -> None:
        """Turn the light on or off."""
        if self._lifx_device is None:
            raise RuntimeError(f"LIFX device {self.id} not connected")

        try:
            power = 65535 if on else 0
            await self._run_sync(self._lifx_device.set_power, power)
            self.is_on = on
            self.status = DeviceStatus.ONLINE
        except Exception as e:
            logger.error(f"Failed to set power for LIFX {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE
            raise

    async def set_brightness(self, brightness: int) -> None:
        """Set brightness (0-100)."""
        if self._lifx_device is None:
            raise RuntimeError(f"LIFX device {self.id} not connected")

        try:
            # Clamp brightness
            brightness = max(0, min(100, brightness))

            # Get current color to preserve hue/sat/kelvin
            color = await self._run_sync(self._lifx_device.get_color)
            if color:
                hue, saturation, _, kelvin = color
                # Convert brightness to LIFX scale
                lifx_brightness = int((brightness / 100.0) * 65535)
                await self._run_sync(
                    self._lifx_device.set_color, [hue, saturation, lifx_brightness, kelvin]
                )

            self.brightness = brightness
            # Turn on if setting brightness > 0
            if brightness > 0 and not self.is_on:
                await self.set_power(True)
            self.status = DeviceStatus.ONLINE
        except Exception as e:
            logger.error(f"Failed to set brightness for LIFX {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE
            raise

    async def set_color(self, color: str) -> None:
        """Set color using hex code."""
        if self._lifx_device is None:
            raise RuntimeError(f"LIFX device {self.id} not connected")

        if not self.supports_color:
            raise ValueError(f"LIFX device {self.id} does not support color")

        try:
            hue, saturation, brightness, kelvin = hex_to_hsbk(color)
            await self._run_sync(
                self._lifx_device.set_color, [hue, saturation, brightness, kelvin]
            )
            self.color = color
            self.status = DeviceStatus.ONLINE

            # Turn on if not already
            if not self.is_on:
                await self.set_power(True)
        except Exception as e:
            logger.error(f"Failed to set color for LIFX {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE
            raise

    async def set_color_temp(self, kelvin: int) -> None:
        """Set color temperature in Kelvin."""
        if self._lifx_device is None:
            raise RuntimeError(f"LIFX device {self.id} not connected")

        try:
            # Clamp kelvin to valid range
            kelvin = max(1500, min(9000, kelvin))

            # Get current brightness
            color = await self._run_sync(self._lifx_device.get_color)
            if color:
                _, _, brightness, _ = color
                # Set white color with specified temperature
                # Hue=0, Saturation=0 = white
                await self._run_sync(
                    self._lifx_device.set_color, [0, 0, brightness, kelvin]
                )

            self.color_temp = kelvin
            self.color = None  # Clear color when setting temp
            self.status = DeviceStatus.ONLINE

            # Turn on if not already
            if not self.is_on:
                await self.set_power(True)
        except Exception as e:
            logger.error(f"Failed to set color temp for LIFX {self.id}: {e}")
            self.status = DeviceStatus.OFFLINE
            raise


async def create_lifx_light(device_config: DeviceConfig, secrets: SecretsConfig) -> LifxLight:
    """Factory function to create a LIFX light from config.

    Args:
        device_config: Device configuration
        secrets: Secrets configuration (not used for LIFX but kept for interface consistency)

    Returns:
        Configured LifxLight instance
    """
    # Import lifxlan here to allow graceful handling if not installed
    try:
        import lifxlan
    except ImportError:
        logger.error("lifxlan package not installed. Install with: pip install lifxlan")
        raise

    mac = device_config.config.get("mac")
    ip = device_config.config.get("ip")

    light = LifxLight(
        id=device_config.id,
        name=device_config.name,
        room_id=device_config.room,
        _mac=mac,
        _ip=ip,
    )

    # Try to find the device
    if mac and ip:
        # Direct connection if we have both MAC and IP
        light._lifx_device = lifxlan.Light(mac, ip)
        logger.info(f"Created LIFX light {device_config.id} with MAC {mac} at {ip}")
    elif mac:
        # Try to find by MAC via discovery
        lan = lifxlan.LifxLAN()
        devices = await asyncio.to_thread(lan.get_lights)
        for device in devices:
            device_mac = await asyncio.to_thread(device.get_mac_addr)
            if device_mac and device_mac.lower() == mac.lower():
                light._lifx_device = device
                logger.info(f"Found LIFX light {device_config.id} by MAC {mac}")
                break
        if light._lifx_device is None:
            logger.warning(f"Could not find LIFX light with MAC {mac}")
    else:
        # Try to find by name via discovery
        lan = lifxlan.LifxLAN()
        devices = await asyncio.to_thread(lan.get_lights)
        for device in devices:
            label = await asyncio.to_thread(device.get_label)
            if label and label.lower() == device_config.name.lower():
                light._lifx_device = device
                logger.info(f"Found LIFX light {device_config.id} by name")
                break
        if light._lifx_device is None:
            logger.warning(f"Could not find LIFX light named {device_config.name}")

    # Initial refresh if device was found
    if light._lifx_device:
        await light.refresh()

    return light
