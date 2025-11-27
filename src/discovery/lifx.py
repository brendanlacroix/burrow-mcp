"""LIFX device discovery."""

import asyncio
import sys
from dataclasses import dataclass


@dataclass
class DiscoveredLifx:
    """A discovered LIFX device."""

    mac: str
    ip: str
    label: str
    product: str | None = None
    group: str | None = None
    location: str | None = None


def slugify(name: str) -> str:
    """Convert a name to a slug suitable for device IDs."""
    return name.lower().replace(" ", "_").replace("-", "_")


async def discover_lifx(timeout: float = 5.0, default_room: str | None = None) -> list[DiscoveredLifx]:
    """Discover LIFX devices on the network.

    Args:
        timeout: How long to wait for discovery (seconds)
        default_room: Default room ID to suggest in config output

    Returns:
        List of discovered devices
    """
    try:
        import lifxlan
    except ImportError:
        print("Error: lifxlan package not installed.", file=sys.stderr)
        print("Install with: pip install lifxlan", file=sys.stderr)
        return []

    print(f"Scanning for LIFX devices ({timeout}s timeout)...")
    print()

    # Run discovery in thread since lifxlan is synchronous
    lan = lifxlan.LifxLAN()

    try:
        devices = await asyncio.wait_for(
            asyncio.to_thread(lan.get_lights),
            timeout=timeout + 2,  # Give a bit more time for the thread
        )
    except asyncio.TimeoutError:
        print("Discovery timed out.", file=sys.stderr)
        devices = []

    if not devices:
        print("No LIFX devices found.")
        print()
        print("Troubleshooting tips:")
        print("  - Make sure you're on the same network as your LIFX bulbs")
        print("  - Check that your firewall allows UDP broadcast (port 56700)")
        print("  - Try increasing the timeout with --timeout 10")
        return []

    discovered = []
    for device in devices:
        try:
            mac = await asyncio.to_thread(device.get_mac_addr)
            ip = device.get_ip_addr()
            label = await asyncio.to_thread(device.get_label)

            # Try to get additional info
            try:
                group = await asyncio.to_thread(device.get_group_label)
            except Exception:
                group = None

            try:
                location = await asyncio.to_thread(device.get_location_label)
            except Exception:
                location = None

            # Get product info if available
            product = None
            try:
                product_info = await asyncio.to_thread(device.get_product)
                if product_info:
                    product = str(product_info)
            except Exception:
                pass

            discovered.append(DiscoveredLifx(
                mac=mac,
                ip=ip,
                label=label,
                product=product,
                group=group,
                location=location,
            ))
        except Exception as e:
            print(f"Warning: Failed to get info for device: {e}", file=sys.stderr)

    # Print results
    print(f"Found {len(discovered)} LIFX device(s):")
    print()

    for d in discovered:
        print(f"  {d.label}")
        print(f"    MAC: {d.mac}")
        print(f"    IP:  {d.ip}")
        if d.group:
            print(f"    Group: {d.group}")
        if d.location:
            print(f"    Location: {d.location}")
        print()

    # Generate config snippet
    print("-" * 60)
    print("Config snippet (add to config/config.yaml under 'devices:'):")
    print("-" * 60)
    print()

    for d in discovered:
        device_id = f"lifx_{slugify(d.label)}"
        room = default_room or slugify(d.group or d.location or "living_room")

        print(f"  - id: {device_id}")
        print(f"    name: \"{d.label}\"")
        print(f"    type: lifx")
        print(f"    room: {room}")
        print(f"    config:")
        print(f"      mac: \"{d.mac}\"")
        print(f"      ip: \"{d.ip}\"")
        print()

    return discovered
