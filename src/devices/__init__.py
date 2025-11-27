"""Device implementations for Burrow MCP."""

from devices.august import AugustLock, create_august_lock
from devices.govee import GoveeLight, create_govee_light
from devices.lifx import LifxLight, create_lifx_light
from devices.manager import DeviceManager
from devices.ring import RingCamera, create_ring_camera
from devices.roomba import RoombaVacuum, create_roomba_vacuum
from devices.tuya import TuyaPlug, create_tuya_plug

__all__ = [
    "AugustLock",
    "DeviceManager",
    "GoveeLight",
    "LifxLight",
    "RingCamera",
    "RoombaVacuum",
    "TuyaPlug",
    "create_august_lock",
    "create_govee_light",
    "create_lifx_light",
    "create_ring_camera",
    "create_roomba_vacuum",
    "create_tuya_plug",
]

# Device type to factory mapping
DEVICE_FACTORIES = {
    "lifx": create_lifx_light,
    "govee": create_govee_light,
    "tuya": create_tuya_plug,
    "august": create_august_lock,
    "roomba": create_roomba_vacuum,
    "ring": create_ring_camera,
}


def register_all_factories(manager: DeviceManager) -> None:
    """Register all device factories with a device manager."""
    for device_type, factory in DEVICE_FACTORIES.items():
        manager.register_device_factory(device_type, factory)
