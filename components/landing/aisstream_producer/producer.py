import asyncio
import json
import logging

import websockets

from config import SETTINGS

async def connect_ais_stream():

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
