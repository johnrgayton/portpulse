import os

from config import SETTINGS


def load_api_key() -> str:
    # Prefer the value in SETTINGS, but fall back to the environment for flexibility.
    api_key = SETTINGS.get("AISSTREAM_API_KEY") or os.getenv("AISSTREAM_API_KEY")
    if not api_key:
        raise RuntimeError("AISSTREAM_API_KEY is required to connect to AISStream")
    return api_key


if __name__ == "__main__":
    # Placeholder to verify configuration wiring before you implement the producer loop.
    _ = load_api_key()
    print("AISStream API key loaded. Ready to start producer loop.")
