import asyncio
import logging
import os
import socket

from app.core.database import db
from app.services.worker_service import WorkerService
from app.services.task_registry import task_registry
from app.services.handlers import add_numbers, slow_task


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("aegis.worker")

POLL_INTERVAL = 1.0
QUEUE_NAME = "default"


async def run_worker() -> None:
    worker_id = f"{socket.gethostname()}-{os.getpid()}"

    # Register supported task handlers once at startup.
    task_registry.register("add_numbers", add_numbers)
    task_registry.register("slow_task", slow_task)

    await db.connect()
    logger.info("Worker %s started", worker_id)

    try:
        while True:
            try:
                # Use a fresh session for each polling iteration.
                async with db.session_factory() as session:
                    service = WorkerService(
                        session,
                        session_factory=db.session_factory
                    )

                    recovered_count = await service.recover_expired_tasks()

                    if recovered_count:
                        logger.warning(
                            "Recovered %s expired task(s)",
                            recovered_count,
                        )

                    task = await service.claim_task(
                        worker_id=worker_id,
                        queue_name=QUEUE_NAME,
                        lease_seconds=60,
                    )

                    if task is not None:
                        logger.info(
                            "Claimed task %s (name=%s, attempt=%s)",
                            task.id,
                            task.name,
                            task.attempts,
                        )
                        # renewed = await service.renew_lease(
                        #     task_id=task.id,
                        #     lease_token=task.lease_token,
                        #     lease_seconds=60,
                        # )

                        await service.execute_task(task)

                        logger.info(
                            "Execution method returned for task %s",
                            task.id,
                        )
                    else:
                        await asyncio.sleep(POLL_INTERVAL)

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Worker iteration failed")
                await asyncio.sleep(POLL_INTERVAL)

    finally:
        if db.engine is not None:
            await db.engine.dispose()

        logger.info("Worker %s stopped", worker_id)


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Worker interrupted")