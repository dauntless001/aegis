from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import Any
from uuid import UUID
from app.utils.enums import TaskStatus

class TaskCreate(BaseModel):
    name: str = Field(
        min_length=1, max_length=255
    )
    queue_name: str = Field(
        default="default", min_length=1, max_length=255
    )
    payload: dict[str, Any]
    scheduled_at: datetime | None = None
    max_attempts: int = Field(default=3, ge=1)


class TaskResponse(BaseModel):
    id: UUID
    name: str
    queue_name: str
    payload: dict[str, Any]
    status: TaskStatus
    scheduled_at: datetime | None = None
    attempts: int
    max_attempts: int
    result: Any | None = None
    last_error: str | None = None
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(
        from_attributes=True
    )


class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
    total: int
    limit: int
    skip: int