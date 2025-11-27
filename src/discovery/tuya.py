"""Tuya device discovery helpers."""

import asyncio
import sys
from dataclasses import dataclass


@dataclass
class DiscoveredTuya:
    """A discovered Tuya device."""

    device_id: str
    ip: str
    version: str
    name: str | None = None
    product_name: str | None = None


def slugify(name: str) -> str:
    """Convert a name to a slug suitable for device IDs."""
    return name.lower().replace(" ", "_").replace("-", "_")


async def discover_tuya(scan: bool = False) -> list[DiscoveredTuya]:
    """Discover Tuya devices or guide through setup.

    Args:
        scan: If True, scan network for devices (requires local keys already)

    Returns:
        List of discovered devices (if scanning)
    """
    try:
        import tinytuya
    except ImportError:
        print("Error: tinytuya package not installed.", file=sys.stderr)
        print("Install with: pip install tinytuya", file=sys.stderr)
        return []

    if scan:
        return await _scan_tuya_devices()
    else:
        _print_tuya_setup_guide()
        return []


async def _scan_tuya_devices() -> list[DiscoveredTuya]:
    """Scan network for Tuya devices."""
    import tinytuya

    print("Scanning for Tuya devices on the network...")
    print("(This requires devices to be in pairing mode or already configured)")
    print()

    # Run scan in thread since it's synchronous
    try:
        devices = await asyncio.to_thread(tinytuya.deviceScan, verbose=False)
    except Exception as e:
        print(f"Scan failed: {e}", file=sys.stderr)
        return []

    if not devices:
        print("No Tuya devices found.")
        print()
        print("Note: Tuya devices may not respond to scans if:")
        print("  - They're not on the same network")
        print("  - They're using a newer protocol version")
        print("  - They haven't been set up yet")
        print()
        print("Run 'burrow discover tuya' (without --scan) for setup instructions.")
        return []

    discovered = []
    for device_id, info in devices.items():
        discovered.append(DiscoveredTuya(
            device_id=device_id,
            ip=info.get("ip", "unknown"),
            version=info.get("version", "3.3"),
            name=info.get("name"),
            product_name=info.get("product_name"),
        ))

    print(f"Found {len(discovered)} Tuya device(s):")
    print()

    for d in discovered:
        print(f"  Device ID: {d.device_id}")
        print(f"    IP: {d.ip}")
        print(f"    Version: {d.version}")
        if d.name:
            print(f"    Name: {d.name}")
        print()

    print("-" * 60)
    print("Note: You still need local keys to control these devices.")
    print("Run 'burrow discover tuya' for instructions on getting local keys.")
    print("-" * 60)

    return discovered


def _print_tuya_setup_guide() -> None:
    """Print guide for setting up Tuya device control."""
    print("=" * 60)
    print("Tuya Device Setup Guide")
    print("=" * 60)
    print()
    print("Tuya devices require 'local keys' for local control.")
    print("Here's how to get them:")
    print()
    print("OPTION 1: Use tinytuya wizard (recommended)")
    print("-" * 40)
    print()
    print("1. Create a Tuya IoT Platform account:")
    print("   https://platform.tuya.com/")
    print()
    print("2. Create a Cloud Project:")
    print("   - Go to Cloud → Development → Create Cloud Project")
    print("   - Select 'Smart Home' for industry")
    print("   - Note your Access ID and Access Secret")
    print()
    print("3. Link your Tuya/Smart Life app:")
    print("   - In your project, go to Devices → Link Tuya App Account")
    print("   - Use the Smart Life or Tuya Smart app to scan the QR code")
    print()
    print("4. Run the tinytuya wizard:")
    print("   python -m tinytuya wizard")
    print()
    print("5. Enter your credentials when prompted")
    print("   The wizard will save device info to devices.json")
    print()
    print()
    print("OPTION 2: Manual extraction")
    print("-" * 40)
    print()
    print("If the wizard doesn't work, you can manually get keys from")
    print("the Tuya IoT Platform:")
    print()
    print("1. Go to Cloud → Development → Your Project → Devices")
    print("2. Click on a device to see its details")
    print("3. The 'Local Key' is what you need")
    print()
    print()
    print("Once you have local keys, add to secrets.yaml:")
    print("-" * 40)
    print()
    print("tuya:")
    print("  plug_living_room:  # matches device id in config.yaml")
    print("    local_key: \"your_local_key_here\"")
    print()
    print()
    print("And add device to config.yaml:")
    print("-" * 40)
    print()
    print("devices:")
    print("  - id: plug_living_room")
    print("    name: \"Living Room Plug\"")
    print("    type: tuya")
    print("    room: living_room")
    print("    config:")
    print("      device_id: \"your_device_id\"")
    print("      ip: \"192.168.1.xxx\"  # optional but faster")
    print()
    print()
    print("To scan for Tuya devices on your network:")
    print("  burrow discover tuya --scan")
    print()
