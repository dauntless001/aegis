
"""Shared pytest fixtures for Aegis integration tests."""

import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base
from app.models.task import Task, TaskAttempt, IdempotencyRecord  # noqa: F401


def get_test_database_url() -> str:
    """Load and validate the dedicated test database URL."""
    url = os.getenv("TEST_DATABASE_URL")

    if not url:
        raise RuntimeError(
            "TEST_DATABASE_URL is required. "
            "Set it to a dedicated PostgreSQL test database."
        )

    if "aegis_test" not in url:
        raise RuntimeError(
            "Refusing to run tests: TEST_DATABASE_URL must target "
            "the dedicated aegis_test database."
        )

    if not url.startswith("postgresql+asyncpg://"):
        raise RuntimeError(
            "TEST_DATABASE_URL must use postgresql+asyncpg://"
        )

    return url


@pytest_asyncio.fixture
async def test_engine():
    """Create test tables in the dedicated test database."""
    database_url = get_test_database_url()
    engine = create_async_engine(database_url, pool_pre_ping=True)

    try:
        async with engine.begin() as connection:
            database_name = await connection.scalar(
                text("SELECT current_database()")
            )
            if database_name != "aegis_test":
                raise RuntimeError(
                    f"Refusing to run tests against {database_name!r}"
                )

            await connection.run_sync(Base.metadata.create_all)

        yield engine

    finally:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)

        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a fresh database session for each test."""
    session_factory = async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with session_factory() as session:
        yield session
        if session.in_transaction():
            await session.rollback()


@pytest.fixture
def session_factory(test_engine):
    """Provide a session factory for worker heartbeat operations."""
    return async_sessionmaker(
        bind=test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
