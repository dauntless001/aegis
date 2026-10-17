from uuid import UUID
from app.models.task import Task
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.enums import TaskStatus
from app.schemas.task import TaskCreate

class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db

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
        task = self.db.get(Task, id)
        return task

    async def create_task(
            self, data: TaskCreate, idempotency_key : str | None = None
        ):
        return ""

        