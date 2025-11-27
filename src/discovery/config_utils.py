"""Configuration utilities for Burrow MCP."""

import sys
from pathlib import Path

EXAMPLE_CONFIG = """\
# Burrow MCP Configuration
# See https://github.com/yourusername/burrow-mcp for documentation

house:
  name: "My Home"
  timezone: "America/New_York"

rooms:
  - id: living_room
    name: Living Room
    floor: 1

  - id: bedroom
    name: Bedroom
    floor: 1

  - id: kitchen
    name: Kitchen
    floor: 1

# Devices are discovered or manually added
# Run 'burrow discover lifx' to find LIFX bulbs
# Run 'burrow discover tuya' for Tuya setup instructions
devices: []

# Scenes are predefined automation sequences
scenes:
  - id: goodnight
    name: Goodnight
    actions:
      - type: room_lights
        room: all
        on: false

  - id: movie
    name: Movie Mode
    actions:
      - type: room_lights
        room: living_room
        on: true
        brightness: 15
        kelvin: 2700
"""

EXAMPLE_SECRETS = """\
# Burrow MCP Secrets
# This file contains sensitive credentials - DO NOT COMMIT TO GIT
# Add this file to .gitignore

# Tuya device local keys (get using 'python -m tinytuya wizard')
tuya: {}
  # plug_living_room:
  #   local_key: "your_local_key_here"

# August smart lock credentials
august: {}
  # username: "email@example.com"
  # password: "xxxxx"
  # lock_id: "XXXXXX"

# Roomba credentials (get using roombapy tools)
roomba: {}
  # blid: "xxxxxxxx"
  # password: "xxxxxxxx"

# Govee API key (from Govee developer portal)
govee: {}
  # api_key: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# MQTT broker for presence sensors
mqtt: {}
  # host: "192.168.1.xxx"
  # port: 1883
  # username: "burrow"
  # password: "xxxxx"
"""


def validate_config(config_dir: str | None = None) -> bool:
    """Validate configuration files.

    Args:
        config_dir: Path to config directory

    Returns:
        True if valid, False otherwise
    """
    from config import find_config_dir, load_config, load_secrets

    if config_dir:
        cfg_path = Path(config_dir)
    else:
        cfg_path = find_config_dir()

    print(f"Validating configuration in: {cfg_path}")
    print()

    errors = []
    warnings = []

    # Check config.yaml exists
    config_file = cfg_path / "config.yaml"
    if not config_file.exists():
        errors.append(f"config.yaml not found at {config_file}")
    else:
        print(f"✓ Found config.yaml")

        # Try to load and validate
        try:
            config = load_config(cfg_path)
            print(f"✓ config.yaml is valid YAML")
            print(f"  House: {config.house.name}")
            print(f"  Rooms: {len(config.rooms)}")
            print(f"  Devices: {len(config.devices)}")
            print(f"  Scenes: {len(config.scenes)}")

            # Check for common issues
            if not config.rooms:
                warnings.append("No rooms defined")

            if not config.devices:
                warnings.append("No devices defined - run 'burrow discover' to find devices")

            # Check device room references
            room_ids = {r.id for r in config.rooms}
            for device in config.devices:
                if device.room and device.room not in room_ids:
                    errors.append(
                        f"Device '{device.id}' references unknown room '{device.room}'"
                    )

            # Check scene references
            device_ids = {d.id for d in config.devices}
            for scene in config.scenes:
                for action in scene.actions:
                    if action.device and action.device not in device_ids:
                        warnings.append(
                            f"Scene '{scene.id}' references unknown device '{action.device}'"
                        )
                    if action.room and action.room != "all" and action.room not in room_ids:
                        warnings.append(
                            f"Scene '{scene.id}' references unknown room '{action.room}'"
                        )

        except Exception as e:
            errors.append(f"Failed to parse config.yaml: {e}")

    print()

    # Check secrets.yaml exists
    secrets_file = cfg_path / "secrets.yaml"
    if not secrets_file.exists():
        warnings.append(f"secrets.yaml not found at {secrets_file}")
        print(f"⚠ secrets.yaml not found (optional)")
    else:
        print(f"✓ Found secrets.yaml")

        # Try to load and validate
        try:
            secrets = load_secrets(cfg_path)
            print(f"✓ secrets.yaml is valid YAML")

            # Check for configured secrets
            has_mqtt = bool(secrets.mqtt.get("host"))
            has_tuya = bool(secrets.tuya)
            has_august = bool(secrets.august.get("lock_id"))

            if has_mqtt:
                print(f"  MQTT: configured ({secrets.mqtt.get('host')})")
            if has_tuya:
                print(f"  Tuya: {len(secrets.tuya)} device(s)")
            if has_august:
                print(f"  August: configured")

        except Exception as e:
            errors.append(f"Failed to parse secrets.yaml: {e}")

    print()

    # Print summary
    if errors:
        print("Errors:")
        for e in errors:
            print(f"  ✗ {e}")
        print()

    if warnings:
        print("Warnings:")
        for w in warnings:
            print(f"  ⚠ {w}")
        print()

    if not errors:
        print("✓ Configuration is valid")
        return True
    else:
        print("✗ Configuration has errors")
        return False


def init_config(config_dir: str = "./config") -> None:
    """Create example configuration files.

    Args:
        config_dir: Path to config directory
    """
    cfg_path = Path(config_dir)

    print(f"Initializing configuration in: {cfg_path}")
    print()

    # Create directory if needed
    if not cfg_path.exists():
        cfg_path.mkdir(parents=True)
        print(f"✓ Created directory: {cfg_path}")

    # Create config.yaml if it doesn't exist
    config_file = cfg_path / "config.yaml"
    if config_file.exists():
        print(f"⚠ config.yaml already exists, skipping")
    else:
        config_file.write_text(EXAMPLE_CONFIG)
        print(f"✓ Created config.yaml")

    # Create secrets.yaml if it doesn't exist
    secrets_file = cfg_path / "secrets.yaml"
    if secrets_file.exists():
        print(f"⚠ secrets.yaml already exists, skipping")
    else:
        secrets_file.write_text(EXAMPLE_SECRETS)
        print(f"✓ Created secrets.yaml")

    # Check/update .gitignore
    gitignore = cfg_path.parent / ".gitignore"
    secrets_pattern = "config/secrets.yaml"

    if gitignore.exists():
        content = gitignore.read_text()
        if secrets_pattern not in content and "secrets.yaml" not in content:
            print()
            print(f"⚠ Warning: secrets.yaml should be in .gitignore")
            print(f"  Add this line to .gitignore: {secrets_pattern}")
    else:
        print()
        print(f"⚠ Warning: No .gitignore found")
        print(f"  Create one and add: {secrets_pattern}")

    print()
    print("Next steps:")
    print("  1. Edit config/config.yaml with your room setup")
    print("  2. Run 'burrow discover lifx' to find LIFX devices")
    print("  3. Run 'burrow discover tuya' for Tuya setup")
    print("  4. Add credentials to config/secrets.yaml")
    print("  5. Run 'burrow config validate' to check your config")
