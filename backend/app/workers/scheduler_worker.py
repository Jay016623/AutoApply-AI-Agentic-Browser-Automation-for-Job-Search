"""Scheduler worker skeleton for periodic orchestration tasks."""

import asyncio

import structlog

from app.config.settings import get_settings
from app.db.redis import get_redis, init_redis_pool
from app.services.retry_scheduler import run_retry_cycle

logger = structlog.get_logger(__name__)


async def run_worker() -> None:
    """Run scheduler loop for retry scheduling and dispatch."""
    settings = get_settings()
    await init_redis_pool(settings.redis_url)
    redis = get_redis()
    if redis is None:
        logger.error("scheduler_worker.redis_unavailable")
        return

    logger.info("scheduler_worker.started")
    while True:
        try:
            await run_retry_cycle(redis)
        except Exception as exc:
            logger.error("scheduler_worker.retry_cycle_failed", error=str(exc))
        await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(run_worker())
