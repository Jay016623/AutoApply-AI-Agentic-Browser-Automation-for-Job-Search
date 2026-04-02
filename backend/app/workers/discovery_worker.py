"""Discovery worker skeleton.

Phase 1 scaffold only. Keeps long-running discovery out of API handlers.
"""

import asyncio

import structlog

logger = structlog.get_logger(__name__)


async def run_worker() -> None:
    """Run discovery loop (skeleton)."""
    logger.info("discovery_worker.started")
    while True:
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run_worker())
