# burrow-mcp

A Python-based home automation system with MCP (Model Context Protocol) interface for Claude integration.

## Features

- Unified control of smart home devices via MCP
- Room-based organization with presence awareness
- Local control preferred, cloud fallback where necessary
- Clean abstractions for adding new device types

## Supported Devices

| Device Type | Brand | Protocol | Status |
|-------------|-------|----------|--------|
| Lights | LIFX | Local LAN | ✅ Implemented |
| Lights | Govee | Cloud + Local UDP | 🔧 Stub |
| Smart Plugs | Tuya-based | Local | ✅ Implemented |
| Locks | August | Cloud | 🔧 Stub |
| Vacuum | Roomba | Local | 🔧 Stub |
| Camera | Ring | Cloud | 🔧 Stub |
| Presence | mmWave/ESP32 | MQTT | ✅ Implemented |

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/burrow-mcp.git
cd burrow-mcp

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .
```

## Configuration

1. Copy the example config files:

```bash
cp config/config.yaml.example config/config.yaml
cp config/secrets.yaml.example config/secrets.yaml
```

2. Edit `config/config.yaml` with your room and device setup.

3. Edit `config/secrets.yaml` with your API keys and credentials.

## Running the MCP Server

```bash
# With uv
uv run python -m burrow.main

# Or directly
python -m burrow.main
```

## Claude Desktop Integration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "burrow": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/burrow-mcp", "python", "-m", "burrow.main"]
    }
  }
}
```

## Available MCP Tools

### Query Tools

- `list_rooms` - List all rooms with their current state
- `get_room_state` - Get detailed state of a specific room
- `list_devices` - List devices with optional filters
- `get_device_state` - Get detailed state of a specific device
- `get_presence` - Get current presence information

### Light Control

- `set_light_power` - Turn a light on or off
- `set_light_brightness` - Set brightness (0-100%)
- `set_light_color` - Set color (hex code)
- `set_light_temperature` - Set color temperature (Kelvin)
- `set_room_lights` - Control all lights in a room

### Plug Control

- `set_plug_power` - Turn a smart plug on or off

### Lock Control

- `lock_door` - Lock a door
- `unlock_door` - Unlock a door

### Vacuum Control

- `start_vacuum` - Start cleaning
- `stop_vacuum` - Stop cleaning
- `dock_vacuum` - Return to dock

### Scenes

- `list_scenes` - List available scenes
- `activate_scene` - Activate a predefined scene

## Getting Tuya Local Keys

Tuya plugs require local keys for local control:

```bash
python -m tinytuya wizard
```

This requires a Tuya IoT developer account (free).

## mmWave Presence Sensors

Recommended hardware: ESP32 + HLK-LD2410 sensor with ESPHome firmware.

Example ESPHome config:

```yaml
ld2410:

binary_sensor:
  - platform: ld2410
    has_target:
      name: "Presence"

mqtt:
  broker: 192.168.1.xxx
  topic_prefix: burrow/presence/living_room
```

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
uv run pytest

# Run linting
uv run ruff check .

# Format code
uv run ruff format .
```

## License

MIT
