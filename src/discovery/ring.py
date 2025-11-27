"""Ring device discovery and authentication helper."""

import asyncio
import sys

from config import SecretsConfig


async def discover_ring(secrets: SecretsConfig | None = None) -> None:
    """Discover Ring devices and guide through authentication.

    Args:
        secrets: Optional secrets config for authentication
    """
    try:
        from ring_doorbell import Auth, Ring
    except ImportError:
        print("Ring doorbell package not installed.")
        print()
        print("Install with:")
        print("  pip install ring-doorbell")
        print()
        return

    from devices.ring import (
        TOKEN_CACHE_PATH,
        _load_cached_token,
        _token_updated_callback,
        list_ring_devices,
    )

    print("=" * 60)
    print("Ring Device Discovery")
    print("=" * 60)
    print()

    # Check for cached token
    cached_token = _load_cached_token()

    if cached_token:
        print("Found cached authentication token.")
        print()

        try:
            auth = Auth("BurrowMCP/1.0", cached_token, _token_updated_callback)
            ring = Ring(auth)
            await asyncio.to_thread(ring.update_data)
            print("✓ Authentication valid!")
            print()
        except Exception as e:
            print(f"✗ Cached token is invalid: {e}")
            print()
            cached_token = None

    # Check secrets for refresh token
    if not cached_token and secrets and secrets.ring.get("refresh_token"):
        print("Found refresh token in secrets.yaml.")
        print()

        try:
            token = {"refresh_token": secrets.ring["refresh_token"]}
            auth = Auth("BurrowMCP/1.0", token, _token_updated_callback)
            ring = Ring(auth)
            await asyncio.to_thread(ring.update_data)
            print("✓ Authentication valid!")
            print()
            cached_token = token
        except Exception as e:
            print(f"✗ Refresh token is invalid: {e}")
            print()

    # If no valid auth, offer interactive setup
    if not cached_token:
        print("No valid Ring authentication found.")
        print()
        print("Ring requires interactive authentication with 2FA.")
        print()
        print("Options:")
        print("  1. Run interactive authentication now")
        print("  2. Exit and authenticate later")
        print()

        choice = input("Enter choice (1 or 2): ").strip()

        if choice == "1":
            print()
            await _interactive_auth()
            print()
        else:
            print()
            print("To authenticate later, run:")
            print("  burrow discover ring --auth")
            print()
            return

    # List devices
    if secrets:
        print("-" * 40)
        print("Available Ring Devices")
        print("-" * 40)
        print()

        devices = await list_ring_devices(secrets)

        if not devices:
            # Try without secrets (using cached token)
            from devices.ring import _load_cached_token

            cached = _load_cached_token()
            if cached:
                # Create minimal secrets with the cached token
                from pydantic import BaseModel

                class TempSecrets(BaseModel):
                    ring: dict = {"refresh_token": cached.get("refresh_token", "")}

                    # Stub other required fields
                    tuya: dict = {}
                    august: dict = {}
                    roomba: dict = {}
                    govee: dict = {}
                    mqtt: dict = {}

                devices = await list_ring_devices(TempSecrets())

        if devices:
            for device in devices:
                print(f"  {device['name']}")
                print(f"    ID: {device['device_id']}")
                print(f"    Type: {device['type']}")
                print(f"    Model: {device.get('model', 'unknown')}")
                if device.get("battery") is not None:
                    print(f"    Battery: {device['battery']}%")
                if device.get("has_subscription"):
                    print("    ✓ Ring Protect subscription")
                print()

            print()
            print("To add a device to config.yaml:")
            print()
            print("devices:")
            for device in devices:
                print(f"  - id: ring_{device['name'].lower().replace(' ', '_')}")
                print(f"    name: \"{device['name']}\"")
                print(f"    type: ring_camera")
                print(f"    room: front_door  # adjust as needed")
                print("    config:")
                print(f"      device_id: \"{device['device_id']}\"")
                print()

        else:
            print("No Ring devices found on this account.")
            print()
    else:
        print("Note: Provide secrets config to list devices.")
        print()


async def _interactive_auth() -> bool:
    """Run interactive Ring authentication."""
    try:
        from ring_doorbell import Auth
    except ImportError:
        return False

    from devices.ring import TOKEN_CACHE_PATH, _token_updated_callback

    print("Ring Interactive Authentication")
    print("=" * 40)
    print()
    print("You will receive a 2FA code via email or SMS.")
    print()

    username = input("Ring email: ").strip()
    password = input("Ring password: ").strip()

    if not username or not password:
        print("Email and password are required.")
        return False

    print()
    print("Requesting 2FA code...")

    try:
        auth = Auth("BurrowMCP/1.0", None, _token_updated_callback)

        # This will trigger 2FA
        try:
            await asyncio.to_thread(auth.fetch_token, username, password)
        except Exception as e:
            # Ring returns an error asking for 2FA code
            if "Verification Code" not in str(e) and "2fa" not in str(e).lower():
                print(f"✗ Authentication failed: {e}")
                return False

        print()
        print("Check your email or phone for the 2FA code.")
        print()

        code = input("Enter 2FA code: ").strip()

        if not code:
            print("2FA code is required.")
            return False

        await asyncio.to_thread(auth.fetch_token, username, password, code)

        print()
        print("✓ Authentication successful!")
        print(f"✓ Token cached at: {TOKEN_CACHE_PATH}")
        print()
        print("You can now use Ring devices in burrow-mcp.")

        return True

    except Exception as e:
        print(f"✗ Authentication failed: {e}")
        return False


def print_ring_help() -> None:
    """Print Ring setup instructions."""
    print("=" * 60)
    print("Ring Setup Guide")
    print("=" * 60)
    print()
    print("Ring requires OAuth authentication with 2-factor verification.")
    print()
    print("Step 1: Install the ring-doorbell package")
    print("  pip install ring-doorbell")
    print()
    print("Step 2: Run interactive authentication")
    print("  burrow discover ring")
    print()
    print("  This will:")
    print("  - Prompt for your Ring email and password")
    print("  - Send a 2FA code to your email/phone")
    print("  - Cache the authentication token locally")
    print()
    print("Step 3: List your Ring devices")
    print("  After authentication, your devices will be listed.")
    print("  Note the device IDs to add to config.yaml.")
    print()
    print("Step 4: Add devices to config.yaml")
    print()
    print("  devices:")
    print("    - id: front_door")
    print('      name: "Front Door"')
    print("      type: ring_camera")
    print("      room: front_door")
    print("      config:")
    print('        device_id: "123456789"')
    print()
    print("Notes:")
    print("  - Ring Protect subscription required for video history")
    print("  - Token is automatically refreshed and cached")
    print("  - Re-run 'burrow discover ring' if token expires")
    print()
