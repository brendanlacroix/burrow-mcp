"""Device implementations for Burrow MCP."""

from devices.appletv import AppleTVDevice, create_appletv_device
from devices.august import AugustLock, create_august_lock
from devices.govee import GoveeLight, create_govee_light
from devices.lifx import LifxLight, create_lifx_light
from devices.manager import DeviceManager
from devices.ring import RingCamera, create_ring_camera
from devices.roomba import RoombaVacuum, create_roomba_vacuum
from devices.roomba_cloud import RoombaCloudVacuum, create_roomba_cloud_vacuum
from devices.tuya import TuyaPlug, create_tuya_plug

__all__ = [
    "AppleTVDevice",
    "AugustLock",
    "DeviceManager",
    "GoveeLight",
    "LifxLight",
    "RingCamera",
    "RoombaVacuum",
    "RoombaCloudVacuum",
    "TuyaPlug",
    "create_appletv_device",
    "create_august_lock",
    "create_govee_light",
    "create_lifx_light",
    "create_ring_camera",
    "create_roomba_vacuum",
    "create_roomba_cloud_vacuum",
    "create_tuya_plug",
]

# Device type to factory mapping
DEVICE_FACTORIES = {
    "lifx": create_lifx_light,
    "govee": create_govee_light,
    "tuya": create_tuya_plug,
    "august": create_august_lock,
    "roomba": create_roomba_vacuum,           # Local MQTT control (older iRobot app)
    "roomba_cloud": create_roomba_cloud_vacuum,  # Cloud API (newer Roomba Home app)
    "ring": create_ring_camera,
    "appletv": create_appletv_device,         # AppleTV media device
}


def register_all_factories(manager: DeviceManager) -> None:
    """Register all device factories with a device manager."""
    for device_type, factory in DEVICE_FACTORIES.items():
        manager.register_device_factory(device_type, factory)
