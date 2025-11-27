"""Configuration loading for Burrow MCP."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class HouseConfig(BaseModel):
    """House-level configuration."""

    name: str = "Home"
    timezone: str = "America/New_York"


class RoomConfig(BaseModel):
    """Room configuration from config file."""

    id: str
    name: str
    floor: int | None = None


class DeviceConfig(BaseModel):
    """Device configuration from config file."""

    id: str
    name: str
    type: str
    room: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class SceneAction(BaseModel):
    """A single action within a scene."""

    type: str
    room: str | None = None
    device: str | None = None
    on: bool | None = None
    brightness: int | None = None
    color: str | None = None
    kelvin: int | None = None
    action: str | None = None


class SceneConfig(BaseModel):
    """Scene configuration."""

    id: str
    name: str
    actions: list[SceneAction] = Field(default_factory=list)


class BurrowConfig(BaseModel):
    """Main configuration model."""

    house: HouseConfig = Field(default_factory=HouseConfig)
    rooms: list[RoomConfig] = Field(default_factory=list)
    devices: list[DeviceConfig] = Field(default_factory=list)
    scenes: list[SceneConfig] = Field(default_factory=list)


class SecretsConfig(BaseModel):
    """Secrets configuration model."""

    tuya: dict[str, dict[str, str]] = Field(default_factory=dict)
    august: dict[str, str] = Field(default_factory=dict)
    roomba: dict[str, str] = Field(default_factory=dict)
    govee: dict[str, str] = Field(default_factory=dict)
    ring: dict[str, str] = Field(default_factory=dict)
    mqtt: dict[str, Any] = Field(default_factory=dict)


def find_config_dir() -> Path:
    """Find the config directory.

    Looks for config directory in the following order:
    1. ./config (relative to cwd)
    2. ../config (parent of cwd)
    3. ~/.config/burrow
    """
    cwd = Path.cwd()

    if (cwd / "config").is_dir():
        return cwd / "config"

    if (cwd.parent / "config").is_dir():
        return cwd.parent / "config"

    home_config = Path.home() / ".config" / "burrow"
    if home_config.is_dir():
        return home_config

    return cwd / "config"


def load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file, returning empty dict if not found."""
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_config(config_dir: Path | None = None) -> BurrowConfig:
    """Load the main configuration."""
    if config_dir is None:
        config_dir = find_config_dir()

    config_path = config_dir / "config.yaml"
    data = load_yaml(config_path)
    return BurrowConfig.model_validate(data)


def load_secrets(config_dir: Path | None = None) -> SecretsConfig:
    """Load the secrets configuration."""
    if config_dir is None:
        config_dir = find_config_dir()

    secrets_path = config_dir / "secrets.yaml"
    data = load_yaml(secrets_path)
    return SecretsConfig.model_validate(data)


def get_device_secret(
    secrets: SecretsConfig, device_type: str, device_id: str, key: str
) -> str | None:
    """Get a secret value for a specific device."""
    type_secrets = getattr(secrets, device_type, {})
    if isinstance(type_secrets, dict):
        device_secrets = type_secrets.get(device_id, {})
        if isinstance(device_secrets, dict):
            return device_secrets.get(key)
        return type_secrets.get(key)
    return None
