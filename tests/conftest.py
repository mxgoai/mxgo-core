import os
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import pytest
from sqlalchemy import create_engine, text
from sqlmodel import SQLModel

from mxtoai._logging import get_logger
from mxtoai.db import AsyncDbConnection, DbConnection, init_db_connection

# Import all models to ensure they are registered with SQLModel.metadata

logger = get_logger(__name__)


@pytest.fixture(scope="session")
def monkeypatch_session():
    """Session-scoped monkeypatch fixture."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture(autouse=True, scope="session")
def setup_test_database(monkeypatch_session):
    """Fixture to set up the test database: drop all tables, run migrations."""
    # Always unset production database variables when running tests
    # This ensures we never accidentally connect to production database
    prod_db_vars = ["DB_USER", "DB_PASSWORD", "DB_NAME", "DB_HOST", "DB_PORT"]
    for var in prod_db_vars:
        if var in os.environ:
            monkeypatch_session.delenv(var, raising=False)

    test_db_url = os.environ.get("TEST_DB_URL")
    if not test_db_url:
        logger.info("TEST_DB_URL not set. Skipping database setup for tests.")
        yield
        return

    logger.info(f"Using TEST_DB_URL for tests: {test_db_url}")

    # Convert async URL to sync URL for sync operations
    sync_test_db_url = test_db_url.replace("+asyncpg", "") if "+asyncpg" in test_db_url else test_db_url

    # Parse URL to set individual environment variables for alembic compatibility
    parsed_url = urlparse(test_db_url)
    monkeypatch_session.setenv("DB_USER", parsed_url.username or "")
    monkeypatch_session.setenv("DB_PASSWORD", parsed_url.password or "")
    monkeypatch_session.setenv("DB_NAME", parsed_url.path.lstrip("/") or "")
    monkeypatch_session.setenv("DB_HOST", parsed_url.hostname or "")
    monkeypatch_session.setenv("DB_PORT", str(parsed_url.port or ""))

    # Patch the database connection methods to use test database for test code
    def get_test_db_uri_sync(cls):
        return sync_test_db_url

    def get_test_db_uri_async(cls):
        # Ensure async URL has asyncpg
        if "+asyncpg" not in test_db_url:
            return test_db_url.replace("postgresql://", "postgresql+asyncpg://")
        return test_db_url

    monkeypatch_session.setattr(DbConnection, "get_db_uri_from_env", classmethod(get_test_db_uri_sync))
    monkeypatch_session.setattr(AsyncDbConnection, "get_db_uri_from_env", classmethod(get_test_db_uri_async))

    # Synchronous engine for dropping tables
    sync_engine = create_engine(sync_test_db_url)

    try:
        logger.info(f"Dropping all tables from test database: {sync_test_db_url}")
        SQLModel.metadata.drop_all(sync_engine)
        logger.info("All tables dropped successfully from test database.")

        # Explicitly drop alembic_version table
        with sync_engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version;"))
            conn.commit()
        logger.info("Explicitly dropped alembic_version table.")

        sync_engine.dispose()
    except Exception as e:
        logger.error(f"Failed to drop tables: {e}")
        pytest.fail(f"Failed to drop tables from {sync_test_db_url}: {e}")

    # Run Alembic migrations
    alembic_cfg_path = Path.cwd() / "mxtoai" / "db" / "alembic.ini"
    logger.info(f"Running Alembic migrations with config: {alembic_cfg_path}")

    if not alembic_cfg_path.exists():
        msg = f"Alembic config file not found at {alembic_cfg_path}. Cannot run migrations."
        logger.error(msg)
        pytest.fail(msg)

    try:
        # Change to the directory containing alembic.ini
        original_cwd = Path.cwd()
        alembic_dir = alembic_cfg_path.parent
        os.chdir(alembic_dir)

        result = subprocess.run(  # noqa: S603
            ["alembic", "-c", "alembic.ini", "upgrade", "head"],  # noqa: S607
            check=True,
            capture_output=True,
            text=True
        )
        logger.info(f"Alembic upgrade to head completed on {sync_test_db_url}")
        logger.info(f"Alembic stdout: {result.stdout}")

        # Change back to original directory
        os.chdir(original_cwd)

    except subprocess.CalledProcessError as e:
        os.chdir(original_cwd)  # Ensure we change back even on error
        logger.error(f"Alembic migration failed. Return code: {e.returncode}")
        logger.error(f"Alembic stdout: {e.stdout}")
        logger.error(f"Alembic stderr: {e.stderr}")
        pytest.fail("Alembic migration failed, aborting tests. Check logs for details.")
    except Exception as e:
        os.chdir(original_cwd)  # Ensure we change back even on error
        logger.error(f"An unexpected error occurred during Alembic migrations: {e}")
        pytest.fail("Unexpected error during Alembic migrations, aborting tests.")

    yield

    logger.info("Test database session completed.")


@pytest.fixture(autouse=True)
def clean_database():
    """Clean database between tests by truncating all tables."""
    test_db_url = os.environ.get("TEST_DB_URL")
    if not test_db_url:
        yield
        return

    yield

    try:
        # Clean up after each test
        db_connection = init_db_connection()
        with db_connection.get_session() as session:
            # Get all table names and truncate them
            result = session.execute(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'"))
            tables = [row[0] for row in result.fetchall()]

            if tables:
                # Disable foreign key checks temporarily
                session.execute(text("SET session_replication_role = replica"))

                # Truncate all tables
                for table in tables:
                    session.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))

                # Re-enable foreign key checks
                session.execute(text("SET session_replication_role = DEFAULT"))

                session.commit()
    except Exception as e:
        # If database cleanup fails, log but continue with tests
        logger.warning(f"Database cleanup failed: {e}")
