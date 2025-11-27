"""CLI entry point for Burrow MCP."""

import argparse
import asyncio
import sys


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="burrow",
        description="Burrow MCP - Home automation with Claude integration",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # serve command
    serve_parser = subparsers.add_parser("serve", help="Run the MCP server")
    serve_parser.add_argument(
        "--config-dir",
        type=str,
        help="Path to config directory",
    )

    # discover command
    discover_parser = subparsers.add_parser("discover", help="Discover devices on the network")
    discover_subparsers = discover_parser.add_subparsers(dest="discover_type", help="Device type")

    # discover lifx
    lifx_parser = discover_subparsers.add_parser("lifx", help="Discover LIFX bulbs via mDNS")
    lifx_parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Discovery timeout in seconds (default: 5)",
    )
    lifx_parser.add_argument(
        "--room",
        type=str,
        help="Default room ID to assign to discovered devices",
    )

    # discover tuya
    tuya_parser = discover_subparsers.add_parser("tuya", help="Help with Tuya device setup")
    tuya_parser.add_argument(
        "--scan",
        action="store_true",
        help="Scan network for Tuya devices (requires local keys already)",
    )

    # discover mqtt
    mqtt_parser = discover_subparsers.add_parser("mqtt", help="Scan MQTT broker for topics")
    mqtt_parser.add_argument(
        "--host",
        type=str,
        default="localhost",
        help="MQTT broker host (default: localhost)",
    )
    mqtt_parser.add_argument(
        "--port",
        type=int,
        default=1883,
        help="MQTT broker port (default: 1883)",
    )
    mqtt_parser.add_argument(
        "--username",
        type=str,
        help="MQTT username",
    )
    mqtt_parser.add_argument(
        "--password",
        type=str,
        help="MQTT password",
    )
    mqtt_parser.add_argument(
        "--topic",
        type=str,
        default="#",
        help="Topic pattern to subscribe to (default: #)",
    )
    mqtt_parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="How long to listen for messages (default: 10)",
    )

    # discover network
    network_parser = discover_subparsers.add_parser(
        "network", help="General network scan (mDNS/SSDP)"
    )
    network_parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Discovery timeout in seconds (default: 5)",
    )

    # discover ring
    ring_parser = discover_subparsers.add_parser("ring", help="Ring device setup")
    ring_parser.add_argument(
        "--auth",
        action="store_true",
        help="Run interactive authentication only",
    )
    ring_parser.add_argument(
        "--help-only",
        action="store_true",
        help="Show Ring setup instructions",
    )

    # config command
    config_parser = subparsers.add_parser("config", help="Configuration utilities")
    config_subparsers = config_parser.add_subparsers(dest="config_action", help="Config action")

    # config validate
    validate_parser = config_subparsers.add_parser("validate", help="Validate configuration")
    validate_parser.add_argument(
        "--config-dir",
        type=str,
        help="Path to config directory",
    )

    # config init
    init_parser = config_subparsers.add_parser("init", help="Create example config files")
    init_parser.add_argument(
        "--config-dir",
        type=str,
        default="./config",
        help="Path to config directory (default: ./config)",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "serve":
        from main import main as serve_main
        asyncio.run(serve_main())

    elif args.command == "discover":
        if args.discover_type is None:
            discover_parser.print_help()
            sys.exit(1)
        asyncio.run(run_discovery(args))

    elif args.command == "config":
        if args.config_action is None:
            config_parser.print_help()
            sys.exit(1)
        run_config_command(args)


async def run_discovery(args: argparse.Namespace) -> None:
    """Run device discovery."""
    if args.discover_type == "lifx":
        from discovery.lifx import discover_lifx
        await discover_lifx(timeout=args.timeout, default_room=args.room)

    elif args.discover_type == "tuya":
        from discovery.tuya import discover_tuya
        await discover_tuya(scan=args.scan)

    elif args.discover_type == "mqtt":
        from discovery.mqtt import scan_mqtt
        await scan_mqtt(
            host=args.host,
            port=args.port,
            username=args.username,
            password=args.password,
            topic=args.topic,
            timeout=args.timeout,
        )

    elif args.discover_type == "network":
        from discovery.network import scan_network
        await scan_network(timeout=args.timeout)

    elif args.discover_type == "ring":
        from discovery.ring import discover_ring, print_ring_help

        if args.help_only:
            print_ring_help()
        else:
            from config import load_secrets, find_config_dir

            try:
                secrets = load_secrets(find_config_dir())
            except Exception:
                secrets = None
            await discover_ring(secrets=secrets)


def run_config_command(args: argparse.Namespace) -> None:
    """Run config commands."""
    if args.config_action == "validate":
        from discovery.config_utils import validate_config
        validate_config(args.config_dir)

    elif args.config_action == "init":
        from discovery.config_utils import init_config
        init_config(args.config_dir)


if __name__ == "__main__":
    main()
