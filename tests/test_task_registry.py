
import pytest

from app.services.task_registry import TaskRegistry
from app.services.handlers import add_numbers


@pytest.mark.asyncio
async def test_registry_returns_registered_handler():
    registry = TaskRegistry()

    registry.register("add_numbers", add_numbers)

    handler = registry.get("add_numbers")
    result = await handler({"a": 10, "b": 20})

    assert result == {"sum": 30}


def test_registry_rejects_duplicate_handler():
    registry = TaskRegistry()

    registry.register("add_numbers", add_numbers)

    with pytest.raises(
        ValueError,
        match="Handler already registered: add_numbers",
    ):
        registry.register("add_numbers", add_numbers)


def test_registry_rejects_unknown_handler():
    registry = TaskRegistry()

    with pytest.raises(
        ValueError,
        match="No handler registered for task: unknown_task",
    ):
        registry.get("unknown_task")
