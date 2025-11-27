"""General network scanner using mDNS and SSDP."""

import asyncio
import socket
import sys
from dataclasses import dataclass


@dataclass
class DiscoveredService:
    """A discovered network service."""

    name: str
    service_type: str
    host: str
    port: int
    properties: dict[str, str]


async def scan_network(timeout: float = 5.0) -> list[DiscoveredService]:
    """Scan network for devices using mDNS/Zeroconf.

    Args:
        timeout: How long to scan for (seconds)

    Returns:
        List of discovered services
    """
    discovered: list[DiscoveredService] = []

    # Try mDNS/Zeroconf first
    zeroconf_results = await _scan_zeroconf(timeout)
    discovered.extend(zeroconf_results)

    # Print results
    if not discovered:
        print("No devices discovered via mDNS.")
        print()
        print("This could mean:")
        print("  - No mDNS-enabled devices on the network")
        print("  - Firewall blocking mDNS (UDP port 5353)")
        print("  - Devices on a different network/VLAN")
        print()
        print("Try device-specific discovery instead:")
        print("  burrow discover lifx     # For LIFX bulbs")
        print("  burrow discover tuya     # For Tuya devices")
        print("  burrow discover mqtt     # For MQTT sensors")
        return []

    # Group by likely device type
    lifx_services = []
    homekit_services = []
    esphome_services = []
    hue_services = []
    other_services = []

    for service in discovered:
        stype = service.service_type.lower()
        name = service.name.lower()

        if "lifx" in stype or "lifx" in name:
            lifx_services.append(service)
        elif "_hap._tcp" in stype or "homekit" in name:
            homekit_services.append(service)
        elif "esphome" in stype or "esphome" in name:
            esphome_services.append(service)
        elif "_hue" in stype or "philips" in name.lower():
            hue_services.append(service)
        else:
            other_services.append(service)

    print("=" * 60)
    print(f"Network Scan Results ({len(discovered)} services found)")
    print("=" * 60)
    print()

    if lifx_services:
        print("LIFX Devices:")
        for s in lifx_services:
            print(f"  {s.name}")
            print(f"    Host: {s.host}:{s.port}")
        print()
        print("  → Run 'burrow discover lifx' for detailed LIFX discovery")
        print()

    if esphome_services:
        print("ESPHome Devices (likely presence sensors):")
        for s in esphome_services:
            print(f"  {s.name}")
            print(f"    Host: {s.host}:{s.port}")
            if s.properties:
                for k, v in s.properties.items():
                    print(f"    {k}: {v}")
        print()
        print("  → These likely publish to MQTT. Run 'burrow discover mqtt'")
        print()

    if homekit_services:
        print("HomeKit Devices:")
        for s in homekit_services:
            print(f"  {s.name}")
            print(f"    Host: {s.host}:{s.port}")
        print()
        print("  → HomeKit devices aren't directly supported yet")
        print()

    if hue_services:
        print("Philips Hue:")
        for s in hue_services:
            print(f"  {s.name}")
            print(f"    Host: {s.host}:{s.port}")
        print()
        print("  → Hue bridges aren't directly supported yet")
        print()

    if other_services:
        print("Other Services:")
        for s in other_services:
            print(f"  {s.name} ({s.service_type})")
            print(f"    Host: {s.host}:{s.port}")
        print()

    return discovered


async def _scan_zeroconf(timeout: float) -> list[DiscoveredService]:
    """Scan using Zeroconf/mDNS."""
    try:
        from zeroconf import ServiceBrowser, ServiceListener, Zeroconf
        from zeroconf.asyncio import AsyncZeroconf
    except ImportError:
        print("Note: zeroconf package not installed.", file=sys.stderr)
        print("Install for better discovery: pip install zeroconf", file=sys.stderr)
        print()
        # Fall back to basic scan
        return await _basic_mdns_scan(timeout)

    discovered: list[DiscoveredService] = []
    lock = asyncio.Lock()

    class Listener(ServiceListener):
        def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            asyncio.create_task(self._handle_service(zc, type_, name))

        async def _handle_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            info = zc.get_service_info(type_, name)
            if info:
                # Get IP address
                addresses = info.parsed_addresses()
                host = addresses[0] if addresses else "unknown"

                # Get properties
                props = {}
                if info.properties:
                    for k, v in info.properties.items():
                        try:
                            key = k.decode("utf-8") if isinstance(k, bytes) else str(k)
                            val = v.decode("utf-8") if isinstance(v, bytes) else str(v)
                            props[key] = val
                        except Exception:
                            pass

                service = DiscoveredService(
                    name=name,
                    service_type=type_,
                    host=host,
                    port=info.port,
                    properties=props,
                )

                async with lock:
                    discovered.append(service)
                    print(f"  Found: {name} ({type_})")

        def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            pass

        def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
            pass

    # Service types to scan for
    service_types = [
        "_lifx._tcp.local.",
        "_hap._tcp.local.",  # HomeKit
        "_esphomelib._tcp.local.",
        "_hue._tcp.local.",
        "_http._tcp.local.",
        "_googlecast._tcp.local.",
    ]

    print(f"Scanning for mDNS services ({timeout}s timeout)...")
    print()

    azc = AsyncZeroconf()
    listener = Listener()

    browsers = []
    for stype in service_types:
        try:
            browser = ServiceBrowser(azc.zeroconf, stype, listener)
            browsers.append(browser)
        except Exception:
            pass

    # Wait for discovery
    await asyncio.sleep(timeout)

    # Clean up
    for browser in browsers:
        browser.cancel()
    await azc.async_close()

    print()
    return discovered


async def _basic_mdns_scan(timeout: float) -> list[DiscoveredService]:
    """Basic mDNS scan without zeroconf library."""
    print("Running basic mDNS scan...")
    print("(Install 'zeroconf' package for better results)")
    print()

    # This is a very basic implementation
    # Just try to find LIFX devices on the standard port
    discovered = []

    # Try common mDNS addresses
    # This is limited but works without dependencies
    try:
        # Use socket to send mDNS query
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)

        # mDNS multicast address
        mdns_addr = ("224.0.0.251", 5353)

        # Very basic mDNS query for _services._dns-sd._udp.local
        # This is simplified and won't work as well as zeroconf
        query = b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00"
        query += b"\x09_services\x07_dns-sd\x04_udp\x05local\x00"
        query += b"\x00\x0c\x00\x01"

        sock.sendto(query, mdns_addr)

        # Try to receive responses
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < timeout:
            try:
                data, addr = sock.recvfrom(4096)
                print(f"  Response from {addr[0]}")
            except socket.timeout:
                break

        sock.close()

    except Exception as e:
        print(f"Basic scan failed: {e}")

    return discovered
