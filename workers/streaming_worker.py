"""
DXLink streaming worker entry point.

This worker maintains a persistent WebSocket connection to the
TastyTrade DXLink streaming API and publishes market data to Redis.
"""

import asyncio
import logging
import os
import signal
from typing import NoReturn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_streaming_worker() -> NoReturn:
    """Run the DXLink streaming worker."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")

    logger.info("Starting DXLink streaming worker...")
    logger.info(f"  Redis URL: {redis_url}")

    # TODO: Initialize DXLink connection and Redis publisher
    # - Connect to TastyTrade API to get streaming token
    # - Establish WebSocket connection to DXLink
    # - Subscribe to configured symbols
    # - Publish quotes to Redis pub/sub channels

    # Placeholder: keep the worker running
    logger.info("Streaming worker stub running (no subscriptions yet)")
    while True:
        await asyncio.sleep(60)
        logger.debug("Streaming worker heartbeat")


def main() -> None:
    """Main entry point with graceful shutdown."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    shutdown_event = asyncio.Event()

    def handle_signal(sig: signal.Signals) -> None:
        logger.info(f"Received {sig.name}, initiating shutdown...")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_signal, sig)

    try:
        loop.run_until_complete(run_streaming_worker())
    except Exception as e:
        logger.error(f"Streaming worker error: {e}")
        raise
    finally:
        loop.close()
        logger.info("Streaming worker shutdown complete")


if __name__ == "__main__":
    main()
