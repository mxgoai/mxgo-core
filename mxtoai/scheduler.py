"""
APScheduler configuration for scheduled email tasks.

This module configures APScheduler with PostgreSQL backend for persistent scheduling
while keeping the existing Dramatiq email processing infrastructure intact.
"""

import os
from datetime import timezone
from typing import Optional

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import create_engine

from mxtoai._logging import get_logger

logger = get_logger("scheduler")

# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None


def get_db_uri() -> str:
    """Get database URI from environment variables."""
    return f"postgresql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"


def create_scheduler() -> BackgroundScheduler:
    """
    Create and configure APScheduler with PostgreSQL backend.

    Returns:
        BackgroundScheduler: Configured scheduler instance

    """
    # Configure jobstore with PostgreSQL
    db_uri = get_db_uri()
    engine = create_engine(db_uri, pool_pre_ping=True, pool_recycle=3600)

    jobstores = {
        "default": SQLAlchemyJobStore(engine=engine, tablename="apscheduler_jobs")
    }

    # Configure thread pool executor
    max_workers = int(os.environ.get("SCHEDULER_MAX_WORKERS", "5"))
    executors = {
        "default": ThreadPoolExecutor(max_workers=max_workers)
    }

    # Job defaults
    job_defaults = {
        "coalesce": True,  # Combine multiple missed executions into one
        "max_instances": 1,  # Only one instance of each job at a time
        "misfire_grace_time": 300,  # 5 minutes grace time for missed jobs
    }

    # Create scheduler
    scheduler = BackgroundScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone=timezone.utc,  # Use UTC for all scheduling
    )

    # Add event listeners for logging
    scheduler.add_listener(job_executed_listener, EVENT_JOB_EXECUTED)
    scheduler.add_listener(job_error_listener, EVENT_JOB_ERROR)
    scheduler.add_listener(job_missed_listener, EVENT_JOB_MISSED)

    return scheduler


def job_executed_listener(event):
    """Log successful job execution."""
    logger.info(f"Job {event.job_id} executed successfully")


def job_error_listener(event):
    """Log job execution errors."""
    logger.error(f"Job {event.job_id} failed with exception: {event.exception}")


def job_missed_listener(event):
    """Log missed job executions."""
    logger.warning(f"Job {event.job_id} missed its scheduled time")


def get_scheduler() -> BackgroundScheduler:
    """
    Get the global scheduler instance, creating it if necessary.

    Returns:
        BackgroundScheduler: The global scheduler instance

    """
    global _scheduler
    if _scheduler is None:
        _scheduler = create_scheduler()
    return _scheduler


def start_scheduler() -> None:
    """Start the scheduler."""
    scheduler = get_scheduler()
    if not scheduler.running:
        logger.info("Starting APScheduler...")
        scheduler.start()
        logger.info("APScheduler started successfully")

        # Load existing jobs from database
        try:
            jobstore = scheduler._jobstores["default"]
            db_jobs = jobstore.get_all_jobs()
            logger.info(f"Loaded {len(db_jobs)} existing jobs from database")
            for job in db_jobs:
                logger.info(f"  Job: {job.id}, next run: {job.next_run_time}")
        except Exception as e:
            logger.error(f"Failed to load existing jobs from database: {e}")
    else:
        logger.info("APScheduler is already running")


def stop_scheduler() -> None:
    """Stop the scheduler."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        logger.info("Stopping APScheduler...")
        _scheduler.shutdown(wait=True)
        logger.info("APScheduler stopped successfully")
        _scheduler = None


def is_scheduler_running() -> bool:
    """Check if the scheduler is running."""
    global _scheduler
    return _scheduler is not None and _scheduler.running


def add_scheduled_job(job_id: str, cron_expression: str, func, args=None, kwargs=None) -> str:
    """
    Add a job to the scheduler using cron expression.
    This can be called to add jobs to the PostgreSQL jobstore even when
    the scheduler is not running (e.g., from Dramatiq workers).

    Args:
        job_id: Unique identifier for the job
        cron_expression: Standard cron expression (e.g., "0 9 * * 1-5")
        func: Function to execute
        args: Positional arguments for the function
        kwargs: Keyword arguments for the function

    Returns:
        str: The job ID

    Raises:
        ValueError: If cron expression is invalid

    """
    from apscheduler.triggers.cron import CronTrigger

    # Parse cron expression
    try:
        trigger = CronTrigger.from_crontab(cron_expression, timezone=timezone.utc)
    except Exception as e:
        logger.error(f"Invalid cron expression '{cron_expression}': {e}")
        msg = f"Invalid cron expression: {e}"
        raise ValueError(msg) from e

    # If the global scheduler is running, add the job to it directly
    # Otherwise, create a temporary scheduler, start it, add the job, then stop it
    try:
        global_scheduler = get_scheduler()

        if global_scheduler.running:
            # Use the running global scheduler
            global_scheduler.add_job(
                func=func,
                trigger=trigger,
                args=args or [],
                kwargs=kwargs or {},
                id=job_id,
                replace_existing=True,
            )
            logger.info(f"Added job {job_id} to running global scheduler")
        else:
            # Create temporary scheduler, start it, add job, then stop it
            logger.info(f"Global scheduler not running, using temporary scheduler for job {job_id}")

            db_uri = get_db_uri()
            engine = create_engine(db_uri, pool_pre_ping=True, pool_recycle=3600)

            from apscheduler.executors.pool import ThreadPoolExecutor
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
            from apscheduler.schedulers.background import BackgroundScheduler

            jobstores = {
                "default": SQLAlchemyJobStore(engine=engine, tablename="apscheduler_jobs")
            }

            executors = {
                "default": ThreadPoolExecutor(max_workers=1)
            }

            job_defaults = {
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,
            }

            temp_scheduler = BackgroundScheduler(
                jobstores=jobstores,
                executors=executors,
                job_defaults=job_defaults,
                timezone=timezone.utc,
            )

            try:
                # Start scheduler temporarily
                temp_scheduler.start()

                # Add job
                temp_scheduler.add_job(
                    func=func,
                    trigger=trigger,
                    args=args or [],
                    kwargs=kwargs or {},
                    id=job_id,
                    replace_existing=True,
                )

                # Wait a moment for persistence
                import time
                time.sleep(1)

                logger.info(f"Added job {job_id} via temporary scheduler")

            finally:
                # Always stop the temporary scheduler
                temp_scheduler.shutdown(wait=True)

        return job_id
    except Exception as e:
        logger.error(f"Failed to add scheduled job {job_id}: {e}")
        raise


def remove_scheduled_job(job_id: str) -> bool:
    """
    Remove a job from the scheduler.

    Args:
        job_id: Job identifier to remove

    Returns:
        bool: True if job was removed, False if job didn't exist

    """
    scheduler = get_scheduler()

    try:
        scheduler.remove_job(job_id)
        logger.info(f"Removed scheduled job {job_id}")
        return True
    except Exception as e:
        logger.warning(f"Failed to remove job {job_id}: {e}")
        return False


def get_scheduled_jobs() -> list:
    """
    Get list of all scheduled jobs.

    Returns:
        list: List of scheduled jobs

    """
    scheduler = get_scheduler()
    return scheduler.get_jobs()


def reload_jobs_from_database() -> int:
    """
    Reload all jobs from the database jobstore.
    This is useful when other processes have added jobs to the database
    and we want to pick them up without restarting the scheduler.

    Returns:
        int: Number of jobs loaded from database

    """
    scheduler = get_scheduler()

    if not scheduler.running:
        logger.warning("Cannot reload jobs - scheduler is not running")
        return 0

    try:
        # Get the default jobstore (SQLAlchemyJobStore)
        jobstore = scheduler._jobstores["default"]

        # Get all jobs from database
        db_jobs = jobstore.get_all_jobs()

        # Get currently loaded jobs
        current_jobs = scheduler.get_jobs()
        current_job_ids = {job.id for job in current_jobs}

        # Find new jobs that aren't loaded
        new_jobs_count = 0
        for job in db_jobs:
            if job.id not in current_job_ids:
                # This job exists in database but isn't loaded in scheduler
                logger.info(f"Found new job in database: {job.id}, next run: {job.next_run_time}")
                new_jobs_count += 1

        if new_jobs_count > 0:
            # Force scheduler to reload all jobs from jobstore
            # The simplest way is to restart the jobstore connection
            logger.info(f"Reloading {new_jobs_count} new jobs from database...")

            # Remove and re-add the jobstore to force refresh
            scheduler.remove_jobstore("default")

            # Recreate the jobstore
            db_uri = get_db_uri()
            from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
            from sqlalchemy import create_engine

            engine = create_engine(db_uri, pool_pre_ping=True, pool_recycle=3600)
            new_jobstore = SQLAlchemyJobStore(engine=engine, tablename="apscheduler_jobs")

            # Re-add the jobstore
            scheduler.add_jobstore(new_jobstore, "default", replace_existing=True)

            logger.info("Successfully reloaded jobstore with new jobs")

        return new_jobs_count

    except Exception as e:
        logger.error(f"Error reloading jobs from database: {e}")
        return 0


def job_exists(job_id: str) -> bool:
    """
    Check if a job exists in the scheduler.

    Args:
        job_id: Job identifier to check

    Returns:
        bool: True if job exists, False otherwise

    """
    scheduler = get_scheduler()
    try:
        job = scheduler.get_job(job_id)
        return job is not None
    except Exception:
        return False
