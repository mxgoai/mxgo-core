import os
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import Session
from sqlmodel.ext.asyncio.session import AsyncSession


class DbConnection:
    """Synchronous database connection handler."""

    _engine = None

    def __init__(self) -> None:
        pass

    @classmethod
    def get_db_uri_from_env(cls) -> str:
        return f"postgresql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"

    def init_connection(self) -> None:
        """Initialize the database connection."""
        if DbConnection._engine is None:
            self._create_engine()

    def close_connection(self) -> None:
        """Close the database connection."""
        if DbConnection._engine is not None:
            DbConnection._engine.dispose()
            DbConnection._engine = None

    def get_connection(self):
        """Get the database connection engine."""
        if DbConnection._engine is None:
            msg = "DB session isn't initialized. Call init_db_connection() at application startup."
            raise ConnectionError(msg)
        return DbConnection._engine

    @contextmanager
    def get_session(self) -> Generator[Session]:
        """Get a synchronous database session."""
        engine = self.get_connection()

        session = Session(engine)
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
        db_url = self.get_db_uri_from_env()
        DbConnection._engine = create_engine(db_url, pool_pre_ping=True, echo=False)
        return DbConnection._engine


class AsyncDbConnection:
    """Asynchronous database connection handler for future use."""

    _engine: AsyncEngine | None = None

    def __init__(self) -> None:
        pass

    @classmethod
    def get_db_uri_from_env(cls) -> str:
        return f"postgresql+asyncpg://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"

    async def init_connection(self) -> None:
        if AsyncDbConnection._engine is None:
            await self._create_engine()

    async def close_connection(self) -> None:
        if AsyncDbConnection._engine is not None:
            await AsyncDbConnection._engine.dispose()
            AsyncDbConnection._engine = None

    def get_connection(self) -> AsyncEngine:
        if AsyncDbConnection._engine is None:
            msg = "Async DB session isn't initialized"
            raise ConnectionError(msg)
        return AsyncDbConnection._engine

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
        AsyncDbConnection._engine = create_async_engine(db_url, pool_pre_ping=True, echo=False)
        return AsyncDbConnection._engine


db_connection = DbConnection()
async_db_connection = AsyncDbConnection()


def init_db_connection() -> DbConnection:
    """Initialize a synchronous database connection."""
    db_connection.init_connection()
    return db_connection


async def init_async_db_connection() -> AsyncDbConnection:
    """Initialize an asynchronous database connection for future use."""
    await async_db_connection.init_connection()
    return async_db_connection
