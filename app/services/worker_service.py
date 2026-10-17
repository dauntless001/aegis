from uuid import UUID, uuid4
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.task import Task, TaskAttempt
from app.utils.enums import TaskStatus
from sqlalchemy import select
from typing import Any

class WorkerService:
    def __init__(self, db: AsyncSession):
        self.db = db


    async def claim_task(
            self, worker_id: str, queue_name: str = "default",
            lease_seconds: int = 60
        ) -> Task | None:
        now = datetime.now(timezone.utc)

        async with self.db.begin():
            statement = (
                select(Task).where(
                    Task.queue_name==queue_name,
                    Task.status.in_(
                        [TaskStatus.PENDING, TaskStatus.RETRYING]
                    ),
                    Task.scheduled_at <= now,
                    Task.attempts < Task.max_attempts
                ).order_by(
                    Task.scheduled_at, Task.created_at, Task.id
                ).limit(1).with_for_update(skip_locked=True)
            )

            task = await self.db.scalar(statement)

            if task is None:
                return None

            task.status = TaskStatus.RUNNING
            task.locked_by = worker_id
            task.locked_until = now + timedelta(seconds=lease_seconds)
            task.lease_token = uuid4()
            task.attempts += 1
            task.started_at = task.started_at or now
            task.last_error = None

            attempts = TaskAttempt(
                task_id=task.id,
                attempt_number=task.attempts,
                worker_id=worker_id,
                status=TaskStatus.RUNNING,
                started_at=now
            )

            self.db.add(attempts)
            await self.db.flush()

        return task

    async def complete_task(
            self, task_id: UUID, lease_token: UUID, result: Any
        ) -> bool:
        now = datetime.now(timezone.utc)

        async with self.db.begin():
            task = await self.db.scalar(
                select(Task).where(Task.id == task_id).with_for_update()
            )

            if task is None or task.status != TaskStatus.RUNNING or task.lease_token != lease_token:
                return False

            attempt = await self.db.scalar(
                select(TaskAttempt).where(
                    TaskAttempt.task_id == task.id,
                    TaskAttempt.attempt_number == task.attempts,
                    TaskAttempt.status == TaskStatus.RUNNING
                ).with_for_update()
            )

            if attempt is None:
                raise RuntimeError(
                    f"Running attempt not found for task {task_id}"
                )

            task.status = TaskStatus.SUCCEEDED
            task.result = result
            task.last_error = None
            task.completed_at = now

            task.locked_by = None
            task.locked_until = None
            task.lease_token = None

            attempt.status = TaskStatus.SUCCEEDED
            attempt.result = result
            attempt.finished_at = now

        return True

    async def fail_task(self, task_id: UUID, lease_token: UUID, error: str) -> bool:
        now = datetime.now(timezone.utc)

        async with self.db.begin():
            task = await self.db.scalar(
                select(Task).where(
                    Task.id == task_id
                ).with_for_update()
            )

            if task is None or task.status != TaskStatus.RUNNING or task.lease_token != lease_token:
                return False

            attempt = await self.db.scalar(
                select(TaskAttempt).where(
                    TaskAttempt.task_id == task.id,
                    TaskAttempt.attempt_number == task.attempts,
                    TaskAttempt.status == TaskStatus.RUNNING
                ).with_for_update()
            )

            if attempt is None:
                raise RuntimeError(
                    f"Running attempt not found for task {task.id}"
                )

            attempt.status = TaskStatus.FAILED
            attempt.error = error
            attempt.finished_at = now

            task.last_error = error

            if task.attempts < task.max_attempts:
                delay_seconds = min(2 ** task.attempts, 300)
                task.status = TaskStatus.RETRYING
                task.scheduled_at = now + timedelta(seconds=delay_seconds)
                task.completed_at = None

            else:
                task.status = TaskStatus.FAILED
                task.completed_at = now

            task.locked_by = None
            task.locked_until = None
            task.lease_token = None

        return True


    async def execute_task(self, task) -> None:
        from app.services.task_registry import task_registry

        task_id = task.id
        lease_token = task.lease_token
        task_name = task.name
        payload = task.payload

        if lease_token is None:
            raise RuntimeError(
                f"Claimed task {task.id} has no lease token"
            )

        try:
            handler = task_registry.get(task_name)
            result = await handler(payload)

        except Exception as exec:

            error = f"{type(exec).__name__}: {exec}"

            await self.fail_task(
                task_id=task_id, lease_token=lease_token, error=error
            )
            return

        completed = await self.complete_task(
            task_id=task_id, lease_token=lease_token,
            result=result
        )

        if not completed:
            raise RuntimeError(
                f"Could not complete task {task_id}: "
                "task state or lease token no longer matches"
            )


    
    async def recover_expired_tasks(self, limit: int = 100) -> int:
        now = datetime.now(timezone.utc)
        recovered_count = 0

        async with self.db.begin():
            statement = (
                select(Task)
                .where(
                    Task.status == TaskStatus.RUNNING,
                    Task.locked_until.is_not(None),
                    Task.locked_until <= now,
                )
                .order_by(Task.locked_until, Task.id)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )

            tasks = (await self.db.scalars(statement)).all()

            for task in tasks:
                # Find the attempt that was interrupted.
                attempt_statement = (
                    select(TaskAttempt)
                    .where(
                        TaskAttempt.task_id == task.id,
                        TaskAttempt.attempt_number == task.attempts,
                        TaskAttempt.status == TaskStatus.RUNNING,
                    )
                    .with_for_update()
                )

                attempt = await self.db.scalar(attempt_statement)

                if attempt is not None:
                    attempt.status = TaskStatus.FAILED
                    attempt.error = "Worker lease expired"
                    attempt.finished_at = now

                task.last_error = "Worker lease expired"

                # Invalidate the old worker's ownership.
                task.locked_by = None
                task.locked_until = None
                task.lease_token = None

                if task.attempts < task.max_attempts:
                    delay_seconds = min(2 ** task.attempts, 300)
                    task.status = TaskStatus.RETRYING
                    task.scheduled_at = now + timedelta(
                        seconds=delay_seconds
                    )
                    task.completed_at = None
                else:
                    task.status = TaskStatus.FAILED
                    task.completed_at = now

                recovered_count += 1

        return recovered_count


            