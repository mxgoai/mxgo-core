import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import Session
from sqlmodel.ext.asyncio.session import AsyncSession


class DbConnection:
    _engine: Optional[AsyncEngine] = None
    _sync_engine = None

    def __init__(self) -> None:
        self.db_uri = self.get_db_uri_from_env()
        self.sync_db_uri = self.get_sync_db_uri_from_env()

    @classmethod
    def get_db_uri_from_env(cls) -> str:
        return f"postgresql+asyncpg://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"

    @classmethod
    def get_sync_db_uri_from_env(cls) -> str:
        return f"postgresql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"

    async def init_connection(self) -> None:
        if self._engine is None:
            await self._create_engine()

    def init_sync_connection(self) -> None:
        if self._sync_engine is None:
            self._create_sync_engine()

    async def close_connection(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
        
        if self._sync_engine is not None:
            self._sync_engine.dispose()

    def get_connection(self) -> AsyncEngine:
        if self._engine is None:
            msg = "DB session isn't initialized"
            raise ConnectionError(msg)
        return self._engine

    def get_sync_connection(self):
        if self._sync_engine is None:
            self.init_sync_connection()
        return self._sync_engine

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession]:
        if self._engine is None:
            msg = "DB session isn't initialized"
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

    @contextmanager
    def get_sync_session(self) -> Generator[Session, None, None]:
        """Get a synchronous database session."""
        if self._sync_engine is None:
            self.init_sync_connection()
            
        session = Session(self._sync_engine)
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def _create_engine(self) -> AsyncEngine:
        db_url = self.db_uri
        self._engine = create_async_engine(db_url, pool_pre_ping=True, echo=False)
        return self._engine
        
    def _create_sync_engine(self):
        """Create a synchronous SQLAlchemy engine."""
        db_url = self.sync_db_uri
        self._sync_engine = create_engine(db_url, pool_pre_ping=True, echo=False)
        return self._sync_engine


async def init_db_connection() -> DbConnection:
    db_connection = DbConnection()
    await db_connection.init_connection()
    return db_connection


def init_sync_db_connection() -> DbConnection:
    """Initialize a synchronous database connection."""
    db_connection = DbConnection()
    db_connection.init_sync_connection()
    return db_connection
