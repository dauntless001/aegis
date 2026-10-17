import json, hashlib
from uuid import UUID
from app.models.task import Task, IdempotencyRecord
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.utils.enums import TaskStatus
from app.schemas.task import TaskCreate
from app.core.config import settings

class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

    def hash_task_request(self, data: TaskCreate) -> str:
        """Hash the validated request deterministically."""
        normalized = data.model_dump(mode="json", exclude_unset=False)

        canonical_json = json.dumps(
            normalized,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

        return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

    async def get_tasks(
            self, queue_name: str | None = None,
            status: TaskStatus | None = None,
            limit: int = 20, offset: int = 0
        ) -> tuple[list[Task], int]:

        filters = []

        if queue_name:
            filters.append(queue_name)

        if status is not None:
            filters.append(status)

        query_count = select(
            func.count()
        ).select_from(Task).where(*filters)

        total_query = await self.db.scalar(query_count)

        query = (
            select(Task).where(
                *filters
            ).order_by(
                Task.created_at.desc(), Task.id
            ).limit(limit).offset(offset)
        )

        result = await self.db.scalars(query)
        tasks = list(result.all())

        return tasks, total_query or 0

    async def get_task(self, id: UUID):
        task = await self.db.get(Task, id)
        return task

    async def create_task(
            self, data: TaskCreate, idempotency_key : str | None = None,
            scope: str = settings.default_idempotency_scope,
        ):
        request_hash = self.hash_task_request(data)
        statement = select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key == idempotency_key,
        )

        try:
            async with self.db.begin():
                if idempotency_key is not None:
                    existing = await self.db.scalar(statement)
                    if existing is not None:
                        if existing.request_hash != request_hash:
                            raise ValueError(
                                "The idempotency key has been used by another request"
                            )
            
                        task = await self.db.get(Task, existing.task_id)
                    
                        if task is None:
                            raise RuntimeError(
                                "Idemptency key references a task that doesn't exist"
                            )
                        
                        return task, False
                    
                task_data = data.model_dump(exclude_unset=True)

                if task_data.get("scheduled_at") is None:
                    task_data.pop("scheduled_at", None)

                task = Task(**task_data)
                self.db.add(task)
                await self.db.flush()

                if idempotency_key is not None:
                    record = IdempotencyRecord(
                        scope=settings.default_idempotency_scope,
                        key=idempotency_key,
                        request_hash=request_hash,
                        task_id=task.id
                    )
                    self.db.add(record)
                    await self.db.flush()

            return task, True
        
        except IntegrityError:
            existing = await self.db.scalar(statement)

            if existing is None:
                raise

            if existing.request_hash != request_hash:
                raise ValueError(
                    "This Idempotency-Key was already used with a different request."
                )

            task = await self.db.get(Task, existing.id)

            if task is None:
                raise RuntimeError(
                    "Idempotency record references a task that does not exist."
                )

            return task, False
        