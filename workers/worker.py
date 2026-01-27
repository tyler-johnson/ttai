"""
Temporal worker entry point.

This worker registers activities and workflows with Temporal
and processes tasks from the ttai-queue task queue.
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


async def run_worker() -> NoReturn:
    """Run the Temporal worker."""
    temporal_address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.getenv("TEMPORAL_NAMESPACE", "default")
    task_queue = os.getenv("TEMPORAL_TASK_QUEUE", "ttai-queue")

    logger.info(f"Starting Temporal worker...")
    logger.info(f"  Address: {temporal_address}")
    logger.info(f"  Namespace: {temporal_namespace}")
    logger.info(f"  Task Queue: {task_queue}")

    # TODO: Initialize Temporal client and worker
    # from temporalio.client import Client
    # from temporalio.worker import Worker
    #
    # client = await Client.connect(temporal_address, namespace=temporal_namespace)
    # worker = Worker(
    #     client,
    #     task_queue=task_queue,
    #     workflows=[...],
    #     activities=[...],
    # )
    # await worker.run()

    # Placeholder: keep the worker running
    logger.info("Worker stub running (no activities registered yet)")
    while True:
        await asyncio.sleep(60)
        logger.debug("Worker heartbeat")


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
