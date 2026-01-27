"""
Temporal worker entry point.

This worker registers activities and workflows with Temporal
and processes tasks from the ttai-queue task queue.
"""

import asyncio
import logging
import signal

from temporalio.client import Client
from temporalio.worker import Worker

from activities.data_fetching import fetch_quote
from config import get_settings
from workflows.quote import GetQuoteWorkflow

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_worker() -> None:
    """Run the Temporal worker."""
    settings = get_settings()

    logger.info("Starting Temporal worker...")
    logger.info(f"  Address: {settings.temporal_address}")
    logger.info(f"  Namespace: {settings.temporal_namespace}")
    logger.info(f"  Task Queue: {settings.temporal_task_queue}")

    # Connect to Temporal server
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    logger.info("Connected to Temporal server")

    # Create and run the worker
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[GetQuoteWorkflow],
        activities=[fetch_quote],
    )

    logger.info("Worker started, waiting for tasks...")
    await worker.run()


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
        loop.run_until_complete(run_worker())
    except Exception as e:
        logger.error(f"Worker error: {e}")
        raise
    finally:
        loop.close()
        logger.info("Worker shutdown complete")


if __name__ == "__main__":
    main()
