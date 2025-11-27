"""Light control handlers for Burrow MCP."""

from typing import Any

from devices.manager import DeviceManager


class LightHandlers:
    """Handlers for light control tools."""

    def __init__(self, device_manager: DeviceManager):
        self.device_manager = device_manager

    async def set_light_power(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set light power state."""
        device_id = args["device_id"]
        on = args["on"]

        light = self.device_manager.get_light(device_id)
        if light is None:
            return {"error": f"Light not found: {device_id}"}

        await light.set_power(on)
        return {"success": True, "device_id": device_id, "is_on": light.is_on}

    async def set_light_brightness(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set light brightness."""
        device_id = args["device_id"]
        brightness = args["brightness"]

        light = self.device_manager.get_light(device_id)
        if light is None:
            return {"error": f"Light not found: {device_id}"}

        await light.set_brightness(brightness)
        return {"success": True, "device_id": device_id, "brightness": light.brightness}

    async def set_light_color(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set light color."""
        device_id = args["device_id"]
        color = args["color"]

        light = self.device_manager.get_light(device_id)
        if light is None:
            return {"error": f"Light not found: {device_id}"}

        if not light.supports_color:
            return {"error": f"Light does not support color: {device_id}"}

        await light.set_color(color)
        return {"success": True, "device_id": device_id, "color": light.color}

    async def set_light_temperature(self, args: dict[str, Any]) -> dict[str, Any]:
        """Set light color temperature."""
        device_id = args["device_id"]
        kelvin = args["kelvin"]

        light = self.device_manager.get_light(device_id)
        if light is None:
            return {"error": f"Light not found: {device_id}"}

        await light.set_color_temp(kelvin)
        return {"success": True, "device_id": device_id, "color_temp": light.color_temp}

    async def set_room_lights(self, args: dict[str, Any]) -> dict[str, Any]:
        """Control all lights in a room."""
        room_id = args["room_id"]
        on = args["on"]
        brightness = args.get("brightness")
        color = args.get("color")
        kelvin = args.get("kelvin")

        room = self.device_manager.get_room(room_id)
        if room is None:
            return {"error": f"Room not found: {room_id}"}

        lights = self.device_manager.get_lights(room_id)
        if not lights:
            return {"error": f"No lights found in room: {room_id}"}

        results = []
        for light in lights:
            try:
                await light.set_power(on)
                if on and brightness is not None:
                    await light.set_brightness(brightness)
                if on and color is not None and light.supports_color:
                    await light.set_color(color)
                if on and kelvin is not None:
                    await light.set_color_temp(kelvin)
                results.append({"device_id": light.id, "success": True})
            except Exception as e:
                results.append({"device_id": light.id, "success": False, "error": str(e)})

        return {"room_id": room_id, "results": results}
