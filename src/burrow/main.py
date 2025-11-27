"""Main entry point for Burrow MCP server."""

import asyncio
import logging
import sys
from pathlib import Path

from burrow.config import load_config, load_secrets
from burrow.devices import register_all_factories
from burrow.devices.base import DeviceManager
from burrow.mcp.server import create_server
from burrow.presence.mmwave import PresenceManager, create_presence_manager

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    """Main entry point."""
    logger.info("Starting Burrow MCP server...")

    # Load configuration
    try:
        config = load_config()
        secrets = load_secrets()
        logger.info(f"Loaded config for: {config.house.name}")
    except Exception as e:
        logger.error(f"Failed to load configuration: {e}")
        sys.exit(1)

    # Create device manager
    device_manager = DeviceManager(config, secrets)
    register_all_factories(device_manager)

    # Initialize devices
    try:
        await device_manager.initialize()
        logger.info(f"Initialized {len(device_manager.get_devices())} devices")
    except Exception as e:
        logger.error(f"Failed to initialize devices: {e}")
        # Continue anyway - some devices may have initialized

    # Create presence manager
    presence_manager: PresenceManager | None = None
    if secrets.mqtt:
        try:
            presence_manager = create_presence_manager(secrets)
            # Add sensors from config
            for device_config in config.devices:
                if device_config.type == "mmwave":
                    mqtt_topic = device_config.config.get("mqtt_topic", "")
                    if mqtt_topic and device_config.room:
                        presence_manager.add_sensor(
                            device_config.id,
                            device_config.room,
                            mqtt_topic,
                        )

            # Set up presence callback to update room state
            def on_presence_change(room_id: str, occupied: bool) -> None:
                room = device_manager.get_room(room_id)
                if room:
                    room.occupied = occupied
                    from datetime import datetime
                    room.last_presence_change = datetime.now()
                    logger.info(f"Room {room_id} presence: {occupied}")

            presence_manager.set_presence_callback(on_presence_change)
            await presence_manager.start()
            logger.info("Started presence monitoring")
        except Exception as e:
            logger.warning(f"Failed to start presence manager: {e}")

    # Create and run MCP server
    server = create_server(config, secrets, device_manager, presence_manager)

    try:
        logger.info("MCP server running...")
        await server.run()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        if presence_manager:
            await presence_manager.stop()


def run() -> None:
    """Synchronous entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
