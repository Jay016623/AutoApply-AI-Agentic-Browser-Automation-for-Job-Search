"""Matching worker skeleton for candidate-job scoring queues."""

import asyncio

import structlog

logger = structlog.get_logger(__name__)


async def run_worker() -> None:
    """Run matching loop (skeleton)."""
    logger.info("matching_worker.started")
    while True:
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run_worker())
