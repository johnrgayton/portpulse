import os

# Centralized settings for the AISStream producer.
SETTINGS = {
    # Keep secrets out of source control; pull from environment at runtime.
    "AISSTREAM_API_KEY": os.getenv("AISSTREAM_API_KEY"),
    "EAST_COAST_PORTS_BOXES": [[[24.0, -96.0], [40.0, -70.0]]],
    "MESSAGE_TYPES": ["PositionReport"],
}
