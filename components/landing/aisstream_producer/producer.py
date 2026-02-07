import asyncio
import json
import logging
import websockets
from datetime import datetime
from config import SETTINGS 

async def connect_ais_stream():

    async with websockets.connect("wss://stream.aisstream.io/v0/stream") as websocket:
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
            
            ais_message = message["Message"]["PositionType"]

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(connect_ais_stream())
