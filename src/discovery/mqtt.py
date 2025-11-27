"""MQTT topic scanner for discovering sensors."""

import asyncio
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class MqttMessage:
    """A captured MQTT message."""

    topic: str
    payload: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class TopicSummary:
    """Summary of messages on a topic."""

    topic: str
    message_count: int
    last_payload: str
    payloads: set[str] = field(default_factory=set)


def slugify(name: str) -> str:
    """Convert a name to a slug suitable for device IDs."""
    return name.lower().replace(" ", "_").replace("-", "_").replace("/", "_")


async def scan_mqtt(
    host: str = "localhost",
    port: int = 1883,
    username: str | None = None,
    password: str | None = None,
    topic: str = "#",
    timeout: float = 10.0,
) -> dict[str, TopicSummary]:
    """Scan MQTT broker for active topics.

    Args:
        host: MQTT broker host
        port: MQTT broker port
        username: Optional username
        password: Optional password
        topic: Topic pattern to subscribe to (default: # for all)
        timeout: How long to listen for messages

    Returns:
        Dictionary of topic -> TopicSummary
    """
    try:
        import aiomqtt
    except ImportError:
        print("Error: aiomqtt package not installed.", file=sys.stderr)
        print("Install with: pip install aiomqtt", file=sys.stderr)
        return {}

    print(f"Connecting to MQTT broker at {host}:{port}...")
    print(f"Subscribing to: {topic}")
    print(f"Listening for {timeout} seconds...")
    print()

    topics: dict[str, TopicSummary] = defaultdict(
        lambda: TopicSummary(topic="", message_count=0, last_payload="", payloads=set())
    )

    try:
        async with aiomqtt.Client(
            hostname=host,
            port=port,
            username=username,
            password=password,
        ) as client:
            await client.subscribe(topic)

            try:
                async with asyncio.timeout(timeout):
                    async for message in client.messages:
                        topic_str = str(message.topic)
                        try:
                            payload = message.payload.decode("utf-8")
                        except UnicodeDecodeError:
                            payload = f"<binary: {len(message.payload)} bytes>"

                        if topic_str not in topics:
                            topics[topic_str] = TopicSummary(
                                topic=topic_str,
                                message_count=0,
                                last_payload="",
                                payloads=set(),
                            )

                        summary = topics[topic_str]
                        summary.message_count += 1
                        summary.last_payload = payload
                        summary.payloads.add(payload[:100])  # Truncate for storage

                        # Print live updates
                        print(f"  [{topic_str}] {payload[:80]}")

            except asyncio.TimeoutError:
                pass  # Expected - timeout reached

    except Exception as e:
        print(f"Error connecting to MQTT broker: {e}", file=sys.stderr)
        return {}

    if not topics:
        print()
        print("No messages received.")
        print()
        print("Troubleshooting tips:")
        print("  - Check that the broker host and port are correct")
        print("  - Verify credentials if authentication is required")
        print("  - Make sure devices are publishing to the broker")
        print("  - Try a broader topic pattern like '#'")
        return {}

    # Print summary
    print()
    print("=" * 60)
    print(f"Summary: {len(topics)} topic(s) discovered")
    print("=" * 60)
    print()

    # Group by likely device/sensor
    presence_topics = []
    sensor_topics = []
    other_topics = []

    for topic_str, summary in sorted(topics.items()):
        topic_lower = topic_str.lower()
        if any(kw in topic_lower for kw in ["presence", "occupancy", "motion", "pir", "mmwave"]):
            presence_topics.append(summary)
        elif any(kw in topic_lower for kw in ["sensor", "temperature", "humidity", "binary"]):
            sensor_topics.append(summary)
        else:
            other_topics.append(summary)

    if presence_topics:
        print("Presence/Motion sensors:")
        for s in presence_topics:
            payloads_preview = ", ".join(list(s.payloads)[:3])
            print(f"  {s.topic}")
            print(f"    Messages: {s.message_count}, Values: {payloads_preview}")
        print()

    if sensor_topics:
        print("Other sensors:")
        for s in sensor_topics:
            payloads_preview = ", ".join(list(s.payloads)[:3])
            print(f"  {s.topic}")
            print(f"    Messages: {s.message_count}, Values: {payloads_preview}")
        print()

    if other_topics:
        print("Other topics:")
        for s in other_topics:
            print(f"  {s.topic} ({s.message_count} messages)")
        print()

    # Generate config suggestions for presence sensors
    if presence_topics:
        print("-" * 60)
        print("Config snippet for presence sensors:")
        print("-" * 60)
        print()

        for s in presence_topics:
            # Try to extract room name from topic
            parts = s.topic.split("/")
            room_guess = "unknown_room"
            for part in parts:
                if part.lower() not in ["burrow", "presence", "binary_sensor", "state", "sensor"]:
                    room_guess = slugify(part)
                    break

            sensor_id = f"mmwave_{room_guess}"

            print(f"  - id: {sensor_id}")
            print(f"    name: \"{room_guess.replace('_', ' ').title()} Presence\"")
            print(f"    type: mmwave")
            print(f"    room: {room_guess}")
            print(f"    config:")
            print(f"      mqtt_topic: \"{s.topic}\"")
            print()

    return dict(topics)
