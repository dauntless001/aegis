
import pytest
from sqlalchemy import func, select

from app.models.task import Task
from app.schemas.task import TaskCreate
from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_same_idempotency_key_does_not_create_duplicate_task(
    session_factory,
):
    data = TaskCreate(
        name="idempotency_test",
        queue_name="default",
        payload={"a": 10, "b": 20},
        max_attempts=3,
    )
    idempotency_key = "test-idempotency-key-001"

    async with session_factory() as session:
        service = TaskService(db=session)

        first_task, first_created = await service.create_task(
            data,
            idempotency_key=idempotency_key,
        )

        first_task_id = first_task.id

        assert first_created is True

    async with session_factory() as session:
        service = TaskService(db=session)

        second_task, second_created = await service.create_task(
            data,
            idempotency_key=idempotency_key,
        )

        assert second_created is False
        assert second_task.id == first_task_id

    async with session_factory() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(Task)
            .where(Task.name == "idempotency_test")
        )

        assert count == 1


@pytest.mark.asyncio
async def test_same_idempotency_key_with_different_payload_raises_error(
    session_factory,
):
    idempotency_key = "test-idempotency-key-002"

    first_data = TaskCreate(
        name="idempotency_conflict_test",
        queue_name="default",
        payload={"a": 10, "b": 20},
        max_attempts=3,
    )

    different_data = TaskCreate(
        name="idempotency_conflict_test",
        queue_name="default",
        payload={"a": 100, "b": 200},
        max_attempts=3,
    )

    async with session_factory() as session:
        service = TaskService(db=session)
        await service.create_task(
            first_data,
            idempotency_key=idempotency_key,
        )

    async with session_factory() as session:
        service = TaskService(db=session)

        with pytest.raises(
            ValueError,
            match="The idempotency key has been used by another request",
        ):
            await service.create_task(
                different_data,
                idempotency_key=idempotency_key,
            )
