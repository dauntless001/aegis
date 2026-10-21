from collections.abc import Awaitable, Callable
from typing import Any
from app.services.handlers import add_numbers


TaskHandler = Callable[[dict[str, Any]], Awaitable[Any]]

class TaskRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, TaskHandler] = {}


    def register(self, name : str, handler: TaskHandler) -> None:
        if name in self._handlers:
            raise ValueError(f"Handler already registered: {name}")

        self._handlers[name] = handler

    def get(self, name: str) -> TaskHandler:
        handler = self._handlers.get(name)

        if handler is None:
            raise ValueError(f"No handler registered for task: {name}")

        return handler


task_registry = TaskRegistry()