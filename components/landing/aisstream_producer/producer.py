import asyncio
import json
import logging
import os

import websockets

from confluent_kafka import Producer

from config import SETTINGS

def build_kafka_producer() -> Producer:
    # Keep configuration explicit and fail fast when required values are missing.
    brokers = os.getenv("KAFKA_BROKERS")
    topic = os.getenv("KAFKA_TOPIC")
    if not brokers:
        raise RuntimeError("KAFKA_BROKERS is required to publish to Redpanda")
    if not topic:
        raise RuntimeError("KAFKA_TOPIC is required to publish to Redpanda")

    config = {
        "bootstrap.servers": brokers,
        # Delivery reports are surfaced via producer.poll().
        "enable.idempotence": True,
        "acks": "all",
        "retries": 5,
        "message.timeout.ms": 30000,
    }

    username = os.getenv("KAFKA_USERNAME")
    password = os.getenv("KAFKA_PASSWORD")
    if username and password:
        # Redpanda quickstart enables SCRAM auth by default.
        config.update(
            {
                "security.protocol": os.getenv("KAFKA_SECURITY_PROTOCOL", "SASL_PLAINTEXT"),
                "sasl.mechanism": os.getenv("KAFKA_SASL_MECHANISM", "SCRAM-SHA-256"),
                "sasl.username": username,
                "sasl.password": password,
            }
        )

    return Producer(config)


def delivery_report(err, msg):
    # Log failed deliveries; successful deliveries are verbose and can be noisy.
    if err is not None:
        logging.error("Delivery failed: %s", err)


async def connect_ais_stream():
    producer = build_kafka_producer()
    topic = os.getenv("KAFKA_TOPIC")

    async with websockets.connect(
        "wss://stream.aisstream.io/v0/stream",
        ping_interval=20,
        ping_timeout=20,
        close_timeout=10,
    ) as websocket:
        logging.info("Connected to AIS Stream")

        subscribe_message = {
            "APIKey": SETTINGS["AISSTREAM_API_KEY"],
            "BoundingBoxes": SETTINGS["EAST_COAST_PORTS_BOXES"],
            "FilterMessageTypes": SETTINGS["MESSAGE_TYPES"],
        }

        subscribe_msg_json = json.dumps(subscribe_message)
        await websocket.send(subscribe_msg_json)
        logging.info("Subscription message sent")

        async for message in websocket:
            message = json.loads(message)

            # Safely extract the AIS payload without assuming specific keys exist.
            msg_type = message.get("MessageType")
            payload = message.get("Message", {}).get(msg_type) if msg_type else None

            if msg_type is None:
                # Log the raw message to surface server-side errors or unexpected formats.
                logging.warning("Unexpected message without MessageType: %s", message)
                continue

            logging.info("msg_type=%s payload=%s", msg_type, payload)

            # Publish the raw message; downstream consumers can parse as needed.
            try:
                producer.produce(
                    topic,
                    value=json.dumps(message).encode("utf-8"),
                    on_delivery=delivery_report,
                )
                producer.poll(0)
            except BufferError:
                # Backpressure: wait for queued messages to be delivered, then continue.
                producer.flush(5)
            except Exception:
                logging.exception("Failed to produce message to topic %s", topic)


async def run_with_retries():
    # Retry loop to handle transient disconnects from AISStream.
    backoff = 2
    while True:
        try:
            await connect_ais_stream()
            backoff = 2
        except Exception as exc:
            logging.exception("AISStream connection failed: %s", exc)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_with_retries())
