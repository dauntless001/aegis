
"""PostgreSQL database connection and utilities."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("database")


class Database:
    """Manage PostgreSQL connections and asynchronous sessions."""

    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None

    async def connect(self) -> None:
        """Initialize the connection pool and verify connectivity."""
        if self.engine is not None:
            return

        engine = create_async_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=20,
            pool_timeout=30,
            pool_recycle=1800,
            pool_pre_ping=True,
        )

        try:
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

            self.engine = engine
            self.session_factory = async_sessionmaker(
                bind=engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            logger.info("Successfully connected to PostgreSQL")

        except SQLAlchemyError:
            await engine.dispose()
            logger.exception("Failed to connect to PostgreSQL")
            raise

    async def disconnect(self) -> None:
        """Close the connection pool."""
        if self.engine is not None:
            try:
                await self.engine.dispose()
                logger.info("PostgreSQL connection pool closed")
            finally:
                self.engine = None
                self.session_factory = None

    async def check_connection(self) -> bool:
        """Check whether PostgreSQL is reachable."""
        if self.engine is None:
            return False

        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            logger.exception("PostgreSQL health check failed")
            return False

    async def get_session(self):
        """Yield a database session."""
        if self.session_factory is None:
            raise RuntimeError(
                "Database not initialized. Call connect() first."
            )

        async with self.session_factory() as session:
            yield session


db = Database()


async def get_database():
    """FastAPI dependency for database sessions."""
    async for session in db.get_session():
        yield session
