import os
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import Session
from sqlmodel.ext.asyncio.session import AsyncSession


class DbConnection:
    """Synchronous database connection handler."""

    _engine = None

    def __init__(self) -> None:
        self.db_uri = self.get_db_uri_from_env()

    @classmethod
    def get_db_uri_from_env(cls) -> str:
        return f"postgresql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"

    def init_connection(self) -> None:
        """Initialize the database connection."""
        if self._engine is None:
            self._create_engine()

    def close_connection(self) -> None:
        """Close the database connection."""
        if self._engine is not None:
            self._engine.dispose()

    def get_connection(self):
        """Get the database connection engine."""
        if self._engine is None:
            msg = "DB session isn't initialized"
            raise ConnectionError(msg)
        return self._engine

    @contextmanager
    def get_session(self) -> Generator[Session]:
        """Get a synchronous database session."""
        if self._engine is None:
            self.init_connection()

        session = Session(self._engine)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _create_engine(self):
        """Create a synchronous SQLAlchemy engine."""
        db_url = self.db_uri
        self._engine = create_engine(db_url, pool_pre_ping=True, echo=False)
        return self._engine


class AsyncDbConnection:
    """Asynchronous database connection handler for future use."""

    _engine: Optional[AsyncEngine] = None

    def __init__(self) -> None:
        self.db_uri = self.get_db_uri_from_env()

    @classmethod
    def get_db_uri_from_env(cls) -> str:
        return f"postgresql+asyncpg://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"

    async def init_connection(self) -> None:
        if self._engine is None:
            await self._create_engine()

    async def close_connection(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()

    def get_connection(self) -> AsyncEngine:
        if self._engine is None:
            msg = "Async DB session isn't initialized"
            raise ConnectionError(msg)
        return self._engine

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        if self._engine is None:
            msg = "Async DB session isn't initialized"
            raise ConnectionError(msg)

        async_session = async_sessionmaker(self._engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def _create_engine(self) -> AsyncEngine:
        db_url = self.db_uri
        self._engine = create_async_engine(db_url, pool_pre_ping=True, echo=False)
        return self._engine


def init_db_connection() -> DbConnection:
    """Initialize a synchronous database connection."""
    db_connection = DbConnection()
    db_connection.init_connection()
    return db_connection


async def init_async_db_connection() -> AsyncDbConnection:
    """Initialize an asynchronous database connection for future use."""
    db_connection = AsyncDbConnection()
    await db_connection.init_connection()
    return db_connection
