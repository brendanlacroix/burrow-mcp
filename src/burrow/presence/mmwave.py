"""mmWave presence sensor integration for Burrow MCP."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from burrow.config import SecretsConfig
from burrow.models.presence import PresenceState

logger = logging.getLogger(__name__)


@dataclass
class MmWaveSensor:
    """Represents an mmWave presence sensor."""

    id: str
    room_id: str
    mqtt_topic: str
    occupied: bool = False
    last_update: datetime | None = None


@dataclass
class PresenceManager:
    """Manages presence detection via MQTT-connected mmWave sensors."""

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    _sensors: dict[str, MmWaveSensor] = field(default_factory=dict)
    _state: PresenceState = field(default_factory=PresenceState)
    _client: Any = field(default=None, repr=False)
    _task: asyncio.Task[Any] | None = field(default=None, repr=False)
    _on_presence_change: Callable[[str, bool], None] | None = None

    def add_sensor(self, sensor_id: str, room_id: str, mqtt_topic: str) -> None:
        """Add a sensor to monitor."""
        self._sensors[sensor_id] = MmWaveSensor(
            id=sensor_id,
            room_id=room_id,
            mqtt_topic=mqtt_topic,
        )
        logger.info(f"Added mmWave sensor {sensor_id} for room {room_id}")

    def set_presence_callback(self, callback: Callable[[str, bool], None]) -> None:
        """Set callback to be called when presence changes.

        Callback receives (room_id, occupied).
        """
        self._on_presence_change = callback

    async def start(self) -> None:
        """Start listening for MQTT messages."""
        try:
            import aiomqtt
        except ImportError:
            logger.error("aiomqtt package not installed. Install with: pip install aiomqtt")
            return

        if not self._sensors:
            logger.warning("No mmWave sensors configured")
            return

        self._task = asyncio.create_task(self._mqtt_loop())
        logger.info("Started MQTT presence listener")

    async def stop(self) -> None:
        """Stop listening for MQTT messages."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Stopped MQTT presence listener")

    async def _mqtt_loop(self) -> None:
        """Main MQTT listening loop."""
        import aiomqtt

        while True:
            try:
                async with aiomqtt.Client(
                    hostname=self.mqtt_host,
                    port=self.mqtt_port,
                    username=self.mqtt_username,
                    password=self.mqtt_password,
                ) as client:
                    # Subscribe to all sensor topics
                    for sensor in self._sensors.values():
                        # Subscribe to presence topic - common patterns:
                        # burrow/presence/living_room/binary_sensor/presence/state
                        # or just burrow/presence/living_room
                        await client.subscribe(f"{sensor.mqtt_topic}/#")
                        await client.subscribe(sensor.mqtt_topic)
                        logger.info(f"Subscribed to {sensor.mqtt_topic}")

                    async for message in client.messages:
                        await self._handle_message(str(message.topic), message.payload)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"MQTT connection error: {e}")
                await asyncio.sleep(5)  # Reconnect delay

    async def _handle_message(self, topic: str, payload: bytes) -> None:
        """Handle incoming MQTT message."""
        # Find which sensor this message is for
        sensor = None
        for s in self._sensors.values():
            if topic.startswith(s.mqtt_topic):
                sensor = s
                break

        if sensor is None:
            return

        # Parse payload - handle common formats
        try:
            payload_str = payload.decode("utf-8").strip().lower()
            # Common formats: "on"/"off", "true"/"false", "1"/"0", "occupied"/"clear"
            occupied = payload_str in ("on", "true", "1", "occupied", "detected")
        except Exception as e:
            logger.warning(f"Failed to parse presence payload: {e}")
            return

        # Update sensor state
        old_occupied = sensor.occupied
        sensor.occupied = occupied
        sensor.last_update = datetime.now()

        # Update presence state
        self._state.set_room_presence(sensor.room_id, occupied, sensor.id)

        # Fire callback if state changed
        if occupied != old_occupied and self._on_presence_change:
            self._on_presence_change(sensor.room_id, occupied)

        logger.debug(f"Presence update: {sensor.room_id} = {occupied}")

    def get_presence_state(self) -> PresenceState:
        """Get current presence state."""
        return self._state

    def is_room_occupied(self, room_id: str) -> bool:
        """Check if a specific room is occupied."""
        for sensor in self._sensors.values():
            if sensor.room_id == room_id and sensor.occupied:
                return True
        return False


def create_presence_manager(secrets: SecretsConfig) -> PresenceManager:
    """Create a presence manager from secrets config.

    Args:
        secrets: Secrets configuration containing MQTT settings

    Returns:
        Configured PresenceManager instance
    """
    mqtt_config = secrets.mqtt
    return PresenceManager(
        mqtt_host=mqtt_config.get("host", "localhost"),
        mqtt_port=mqtt_config.get("port", 1883),
        mqtt_username=mqtt_config.get("username"),
        mqtt_password=mqtt_config.get("password"),
    )
