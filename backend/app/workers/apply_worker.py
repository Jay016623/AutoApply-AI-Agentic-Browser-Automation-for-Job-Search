"""Apply worker skeleton for v2 workflow orchestration.

Existing application_worker remains active; this is a Phase 1 seam.
"""

import asyncio

import structlog

logger = structlog.get_logger(__name__)


async def run_worker() -> None:
    """Run apply loop (skeleton)."""
    logger.info("apply_worker.started")
    while True:
        await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(run_worker())
