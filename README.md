# burrow-mcp

A Python-based home automation system with MCP (Model Context Protocol) interface for Claude integration.

## Features

- Unified control of smart home devices via MCP
- Room-based organization with presence awareness
- Local control preferred, cloud fallback where necessary
- Clean abstractions for adding new device types
- Device discovery helpers for easy setup

## Supported Devices

| Device Type | Brand | Protocol | Status |
|-------------|-------|----------|--------|
| Lights | LIFX | Local LAN | Implemented |
| Lights | Govee | Cloud + Local UDP | Stub |
| Smart Plugs | Tuya-based | Local | Implemented |
| Locks | August | Cloud | Stub |
| Vacuum | Roomba | Local | Stub |
| Camera | Ring | Cloud | Stub |
| Presence | mmWave/ESP32 | MQTT | Implemented |

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/burrow-mcp.git
cd burrow-mcp

# Install with uv (recommended)
uv sync

# With discovery extras (for better network scanning)
uv sync --extra discovery

# Or with pip
pip install -e .
```

## Quick Start

```bash
# Initialize config files
burrow config init

# Discover devices on your network
burrow discover lifx          # Find LIFX bulbs
burrow discover tuya          # Tuya setup guide
burrow discover mqtt --host 192.168.1.x  # Scan MQTT topics
burrow discover network       # General mDNS scan

# Validate your configuration
burrow config validate

# Run the MCP server
burrow serve
```

## CLI Commands

### `burrow serve`

Run the MCP server for Claude integration.

```bash
burrow serve
burrow serve --config-dir /path/to/config
```

### `burrow discover`

Discover devices on the network.

```bash
# LIFX bulbs (uses mDNS)
burrow discover lifx
burrow discover lifx --timeout 10
burrow discover lifx --room living_room

# Tuya devices (prints setup guide)
burrow discover tuya
burrow discover tuya --scan  # Scan network (needs local keys first)

# MQTT topics (for presence sensors)
burrow discover mqtt --host 192.168.1.100
burrow discover mqtt --host broker.local --topic "home/#" --timeout 30

# General network scan
burrow discover network
burrow discover network --timeout 10
```

### `burrow config`

Configuration utilities.

```bash
# Create example config files
burrow config init
burrow config init --config-dir ./my-config

# Validate configuration
burrow config validate
burrow config validate --config-dir ./my-config
```

## Configuration

Config files go in `./config/` by default:

### config.yaml

```yaml
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

devices:
  # Run 'burrow discover lifx' to generate these
  - id: lifx_living_main
    name: "Living Room Light"
    type: lifx
    room: living_room
    config:
      mac: "d0:73:d5:xx:xx:xx"
      ip: "192.168.1.100"

scenes:
  - id: goodnight
    name: Goodnight
    actions:
      - type: room_lights
        room: all
        on: false
```

### secrets.yaml

```yaml
# Tuya local keys
tuya:
  plug_living_room:
    local_key: "xxxxxxxxxxxxxxxx"

# MQTT broker
mqtt:
  host: "192.168.1.100"
  port: 1883
```

## Claude Desktop Integration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "burrow": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/burrow-mcp", "burrow", "serve"]
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

## Project Structure

```
burrow-mcp/
├── pyproject.toml
├── config/
│   ├── config.yaml.example
│   └── secrets.yaml.example
├── src/
│   ├── cli.py               # CLI entry point
│   ├── main.py              # MCP server entry
│   ├── config.py            # Config loading
│   ├── models/              # Data models
│   ├── devices/             # Device implementations
│   ├── presence/            # Presence detection
│   ├── state/               # State persistence
│   ├── mcp/                 # MCP server & handlers
│   └── discovery/           # Device discovery
│       ├── lifx.py          # LIFX discovery
│       ├── tuya.py          # Tuya setup helper
│       ├── mqtt.py          # MQTT scanner
│       ├── network.py       # mDNS/SSDP scanner
│       └── config_utils.py  # Config helpers
└── tests/
```

## Development

```bash
# Install dev dependencies
uv sync --dev

# Run tests
PYTHONPATH=src uv run pytest

# Run linting
uv run ruff check src

# Format code
uv run ruff format src
```

## License

MIT
