"""Scheduler worker skeleton for periodic orchestration tasks."""

import asyncio

import structlog

logger = structlog.get_logger(__name__)


async def run_worker() -> None:
    """Run scheduler loop (skeleton)."""
    logger.info("scheduler_worker.started")
    while True:
        await asyncio.sleep(60)


if __name__ == "__main__":
    asyncio.run(run_worker())
