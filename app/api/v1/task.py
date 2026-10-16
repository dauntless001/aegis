from fastapi import APIRouter, Depends, Query
from app.core.database import get_database
from app.schemas.task import (
    TaskListResponse
)
from app.utils.enums import TaskStatus
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get(
    "", 
    response_model=TaskListResponse,
)
def get_lists(
    queue_name: str = None,
    status: TaskStatus | None = Query(default=None, alias="status"),
    limit: int | None = Query(default=0, ge=1, le=100),
    offset: int | None = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_database)
):
    """
    Get All tasks
    """
    return {"details": "Hello"}


@router.get(
    "/{task_id}", 
    response_model=TaskListResponse,
)
def get_lists():
    """
    Get task
    """
    return {"details": "Hello"}