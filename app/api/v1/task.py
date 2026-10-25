from uuid import UUID
from fastapi import (
    APIRouter, Depends, Header, HTTPException, Query, 
    Response, status
)
from app.core.database import get_database
from app.core.logging import get_logger
from app.schemas.task import (
    TaskCreate,
    TaskResponse,
    TaskListResponse
)
from app.utils.enums import TaskStatus
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.task_service import TaskService

router = APIRouter(prefix="/tasks", tags=["Tasks"])
logger = get_logger("api.tasks")

@router.get(
    "", 
    response_model=TaskListResponse,
)
async def get_tasks(
    queue_name: str = None,
    status: TaskStatus | None = Query(default=None, alias="status"),
    limit: int | None = Query(default=20, ge=1, le=100),
    offset: int | None = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_database)
):
    """
    Get All tasks
    """
    service = TaskService(db=db)
    tasks, total = await service.get_tasks(
        queue_name=queue_name,
        status=status,
        limit=limit, offset=offset
    )
    return TaskListResponse(
        tasks=tasks,
        total=total,
        limit=limit,
        skip=0
    )


@router.get(
    "/{id}", 
    response_model=TaskResponse,
)
async def get_task(
    id: UUID,
    db: AsyncSession = Depends(get_database)
):
    """
    Get task
    """
    service = TaskService(db=db)
    task = await service.get_task(id=id)

    if task is None:
        logger.info(
            "Task not found",
            extra={"id": id}
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )
    return task


@router.post(
    "/create", 
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    data: TaskCreate,
    response: Response,
    idempotency_key : str | None = Header(
        default=None,
        alias='Idempotency-Key',
        min_length=1,
        max_length=255
    ),
    db : AsyncSession = Depends(get_database)
):
    task_service = TaskService(db=db)
    try:
        task, created = await task_service.create_task(
            data, idempotency_key=idempotency_key
        )
        if not created:
            response.status_code = status.HTTP_200_OK
            logger.info(
                "Task already created",
                extra={"task": task}
            )
        return task
    except ValueError as exec:
        logger.warning(
            "Task Submission rejected",
            extra={
                "data": data,
                "reason": str(exec)
            }
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exec)
        )

    except Exception:
        logger.error(
            "Unexpected error while submitting task",
            extra={"data": data}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unexpected error while submitting task"
        )


@router.get(
    "/{task_id}/cancel",
    response_model=TaskResponse
)
async def cancel_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_database)
):
    service  = TaskService(db=db)

    try:
        task = await service.cancel_task(task_id=task_id)
    except ValueError as exec:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            details=str(exec)
        )

    if task is None:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            details="Task not found"
        )

    return task


@router.get(
    "/{task_id}/retry",
    response_model=TaskResponse
)
async def cancel_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_database)
):
    service  = TaskService(db=db)

    try:
        task = await service.retry_task(task_id=task_id)
    except ValueError as exec:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            details=str(exec)
        )

    if task is None:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            details="Task not found"
        )

    return task