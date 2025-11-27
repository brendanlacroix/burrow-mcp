"""Main entry point for Burrow MCP server."""

import asyncio
import logging
import sys

from config import load_config, load_secrets
from devices import register_all_factories
from devices.manager import DeviceManager
from mcp_server.server import create_server
from presence import PresenceManager, create_presence_manager

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

    # Create presence manager
    presence_manager: PresenceManager | None = None
    if secrets.mqtt:
        try:
            presence_manager = create_presence_manager(secrets)
            for device_config in config.devices:
                if device_config.type == "mmwave":
                    mqtt_topic = device_config.config.get("mqtt_topic", "")
                    if mqtt_topic and device_config.room:
                        presence_manager.add_sensor(
                            device_config.id,
                            device_config.room,
                            mqtt_topic,
                        )

            def on_presence_change(room_id: str, occupied: bool) -> None:
                # Use device manager's method which also persists state
                asyncio.create_task(
                    device_manager.update_room_presence(room_id, occupied)
                )
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
        # Persist state before shutdown
        await device_manager.shutdown()
        logger.info("Shutdown complete")


def run() -> None:
    """Synchronous entry point."""
    asyncio.run(main())


if __name__ == "__main__":
    run()
