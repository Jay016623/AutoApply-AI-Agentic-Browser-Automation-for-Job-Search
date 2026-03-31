"""Watchdog worker skeleton for stuck-job detection and recovery."""

import asyncio

import structlog

logger = structlog.get_logger(__name__)


async def run_worker() -> None:
    """Run watchdog loop (skeleton)."""
    logger.info("watchdog_worker.started")
    while True:
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(run_worker())
