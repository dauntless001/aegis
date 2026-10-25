from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4
from app.models.base import Base
from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, Enum, ForeignKey, func, 
    Index, Integer, String, Text, text, UniqueConstraint, Uuid, 
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Any
from app.utils.enums import TaskStatus

class Task(Base):
    __tablename__ = "tasks"

    __table_args__ = (
        CheckConstraint("attempts >= 0", name="ck_tasks_attempts_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="ck_tasks_max_attempts_positive"),

        Index(
            "ix_tasks_queue_status_scheduled",
            "queue_name",
            "status",
            "scheduled_at",
        ),
        Index(
            "ix_tasks_expired_leases",
            "locked_until",
            postgresql_where=text("status = 'running'"),
        ),
        Index("ix_tasks_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    queue_name: Mapped[str] = mapped_column(
        String(100),
        default="default",
        server_default="default",
        nullable=False,
    )

    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
    )

    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_status",
            values_callable=lambda enum: [
                item.value for item in enum
            ],
        ),
        default=TaskStatus.PENDING,
        server_default=TaskStatus.PENDING.value,
        nullable=False,
    )

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(), nullable=False
    )

    attempts: Mapped[int] = mapped_column(
        Integer, default=0,
        server_default="0",nullable=False
    )

    max_attempts: Mapped[int] = mapped_column(
        Integer, default=3,
        server_default="3", nullable=False
    )

    locked_by: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Changes when ownership is claimed or reclaimed.
    lease_token: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )

    # Final task output and most recent error.
    result: Mapped[Any | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Execution history.
    attempts_history: Mapped[list[TaskAttempt]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="TaskAttempt.attempt_number",
    )

    # A task may have one submission idempotency record.
    idempotency_record: Mapped[IdempotencyRecord | None] = relationship(
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    cancel_requested: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
        nullable=False
    )


class TaskAttempt(Base):
    """Records one execution attempt of a task."""

    __tablename__ = "task_attempts"

    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "attempt_number",
            name="uq_task_attempts_task_number",
        ),
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_task_attempts_number_positive",
        ),
        Index(
            "ix_task_attempts_worker_started",
            "worker_id",
            "started_at",
        )
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    task_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Starts at 1 for each task.
    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    worker_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    status: Mapped[TaskStatus] = mapped_column(
        Enum(
            TaskStatus,
            name="task_attempt_status",
            values_callable=lambda enum: [
                item.value for item in enum
            ],
        ),
        default=TaskStatus.RUNNING,
        server_default="running",
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    result: Mapped[Any | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    task: Mapped[Task] = relationship(
        back_populates="attempts_history",
    )


class IdempotencyRecord(Base):
    """Associates a client submission key with its original task."""

    __tablename__ = "idempotency_records"

    __table_args__ = (
        UniqueConstraint(
            "scope",
            "key",
            name="uq_idempotency_scope_key",
        ),
        UniqueConstraint(
            "task_id",
            name="uq_idempotency_task_id",
        ),
        Index(
            "ix_idempotency_records_expires_at",
            "expires_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    # Stable ID for the authenticated client or tenant.
    scope: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Provided by the client and reused on retries.
    key: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # SHA-256 hash of normalized request data.
    request_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )

    task_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )

    # NULL means the record has no automatic expiry.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    task: Mapped[Task] = relationship(
        back_populates="idempotency_record",
    )