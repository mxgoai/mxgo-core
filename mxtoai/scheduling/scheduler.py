"""
APScheduler configuration for scheduled email tasks.

This module provides a class-based scheduling implementation that can be instantiated
in different processes while sharing the same PostgreSQL jobstore.
"""

import os
from datetime import datetime, timezone

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from croniter import croniter
from sqlalchemy import create_engine

from mxtoai._logging import get_logger

logger = get_logger("scheduling")

# Constants
CRON_EXPRESSION_PARTS = 5


def is_one_time_task(cron_expression: str) -> bool:
    """
    Determine if a cron expression represents a one-time task.

    Args:
        cron_expression: The cron expression to analyze

    Returns:
        bool: True if this appears to be a one-time task

    """
    parts = cron_expression.strip().split()
    if len(parts) != CRON_EXPRESSION_PARTS:
        return False

    minute, hour, day, month, dayofweek = parts

    # Check if all fields are specific numbers (no wildcards, ranges, or intervals)
    # and day of week is * (meaning specific date)
    return bool(minute.isdigit() and hour.isdigit() and day.isdigit() and month.isdigit() and dayofweek == "*")


class Scheduler:
    """
    Class-based scheduling implementation that can be instantiated in different processes.
    Uses PostgreSQL as the shared jobstore for coordination between processes.
    """

    def __init__(self):
        """
        Initialize the scheduling with PostgreSQL jobstore.
        """
        self.max_workers = 1
        self._scheduler: BackgroundScheduler | None = None
        self._previous_job_ids: set | None = None  # Track previous job IDs for change detection

    def get_db_uri(self) -> str:
        """Get database URI from environment variables."""
        return f"postgresql://{os.environ['DB_USER']}:{os.environ['DB_PASSWORD']}@{os.environ['DB_HOST']}:{os.environ['DB_PORT']}/{os.environ['DB_NAME']}"

    def _create_scheduler(self) -> BackgroundScheduler:
        """
        Create and configure APScheduler with PostgreSQL backend.

        Returns:
            BackgroundScheduler: Configured scheduling instance

        """
        # Configure jobstore with PostgreSQL
        db_uri = self.get_db_uri()
        engine = create_engine(db_uri, pool_pre_ping=True, pool_recycle=3600)

        jobstores = {"default": SQLAlchemyJobStore(engine=engine, tablename="apscheduler_jobs")}

        # Configure thread pool executor
        executors = {"default": ThreadPoolExecutor(max_workers=self.max_workers)}

        # Job defaults
        job_defaults = {
            "coalesce": True,  # Combine multiple missed executions into one
            "max_instances": 1,  # Only one instance of each job at a time
            "misfire_grace_time": 300,  # 5 minutes grace time for missed jobs
        }

        # Create scheduling
        scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=timezone.utc,  # Use UTC for all scheduling
        )

        # Add event listeners for logging
        scheduler.add_listener(self._job_executed_listener, EVENT_JOB_EXECUTED)
        scheduler.add_listener(self._job_error_listener, EVENT_JOB_ERROR)
        scheduler.add_listener(self._job_missed_listener, EVENT_JOB_MISSED)

        return scheduler

    def _job_executed_listener(self, event):
        """Log successful job execution."""
        logger.info(f"Job {event.job_id} executed successfully")

    def _job_error_listener(self, event):
        """Log job execution errors."""
        logger.error(f"Job {event.job_id} failed with exception: {event.exception}")

    def _job_missed_listener(self, event):
        """Log missed job executions."""
        logger.warning(f"Job {event.job_id} missed its scheduled time")

    def get_scheduler(self) -> BackgroundScheduler:
        """
        Get the scheduling instance, creating it if necessary.

        Returns:
            BackgroundScheduler: The scheduling instance

        """
        if self._scheduler is None:
            self._scheduler = self._create_scheduler()
        return self._scheduler

    def start(self) -> None:
        """Start the scheduling."""
        scheduler = self.get_scheduler()
        if not scheduler.running:
            logger.info("Starting APScheduler...")
            scheduler.start()
            logger.info("APScheduler started successfully")

            # Load and log existing jobs from database
            try:
                self.refresh_jobs()
            except Exception as e:
                logger.error(f"Failed to refresh jobs on startup: {e}")
        else:
            logger.info("APScheduler is already running")

    def stop(self) -> None:
        """Stop the scheduling."""
        if self._scheduler is not None and self._scheduler.running:
            logger.info("Stopping APScheduler...")
            self._scheduler.shutdown(wait=True)
            logger.info("APScheduler stopped successfully")
            self._scheduler = None

    def is_running(self) -> bool:
        """Check if the scheduling is running."""
        return self._scheduler is not None and self._scheduler.running

    def refresh_jobs(self) -> None:
        """
        Refresh the scheduling's job list from the PostgreSQL jobstore.
        This is useful when running in separate processes to pick up jobs
        added by other processes.
        """
        scheduler = self.get_scheduler()
        try:
            jobstore = scheduler._jobstores["default"]  # noqa: SLF001
            db_jobs = jobstore.get_all_jobs()

            # Get current job IDs for comparison
            current_job_ids = {job.id for job in db_jobs}

            # Only log if job list has changed
            if self._previous_job_ids != current_job_ids:
                if self._previous_job_ids is None:
                    # First time running - log initial state
                    logger.info(f"Initial job list loaded - found {len(db_jobs)} jobs in database")
                else:
                    # Calculate changes
                    added_jobs = current_job_ids - self._previous_job_ids
                    removed_jobs = self._previous_job_ids - current_job_ids

                    # Log the changes
                    changes = []
                    if added_jobs:
                        changes.append(f"+{len(added_jobs)} added")
                    if removed_jobs:
                        changes.append(f"-{len(removed_jobs)} removed")

                    change_summary = ", ".join(changes)
                    logger.info(f"Job list changed: {change_summary} (total: {len(db_jobs)} jobs)")

                    # Log individual job changes for debugging
                    if added_jobs:
                        logger.debug(f"Added jobs: {sorted(added_jobs)}")
                    if removed_jobs:
                        logger.debug(f"Removed jobs: {sorted(removed_jobs)}")

                # Update previous job IDs for next comparison
                self._previous_job_ids = current_job_ids

            # NOTE: This is a workaround to ensure we can detect new jobs, by default they
            # aren't getting picked up.

            # Find new jobs that aren't loaded
            overdue_jobs = False
            for job in db_jobs:
                current_time = datetime.now(timezone.utc)
                is_job_overdue = job.next_run_time is not None and job.next_run_time < current_time
                overdue_jobs = overdue_jobs or is_job_overdue

            if overdue_jobs:
                # Force scheduler to reload all jobs from jobstore
                # The simplest way is to restart the jobstore connection
                # Remove and re-add the jobstore to force refresh
                scheduler.remove_jobstore("default")
                # Recreate the jobstore
                db_uri = self.get_db_uri()
                engine = create_engine(db_uri, pool_pre_ping=True, pool_recycle=3600)
                new_jobstore = SQLAlchemyJobStore(engine=engine, tablename="apscheduler_jobs")

                # Re-add the jobstore
                scheduler.add_jobstore(new_jobstore, "default", replace_existing=True)
                logger.info("Successfully reloaded jobstore with new jobs")

        except Exception as e:
            logger.error(f"Failed to refresh jobs from database: {e}")
            raise

    def add_job(self, job_id: str, cron_expression: str, func, args=None, kwargs=None) -> str:
        """
        Add a job to the scheduling using cron expression or date trigger for one-time tasks.
        This can be called to add jobs to the PostgreSQL jobstore even when
        the scheduling is not running (e.g., from other processes).

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
        # Determine if this is a one-time task
        if is_one_time_task(cron_expression):
            # For one-time tasks, use DateTrigger instead of CronTrigger
            try:
                # Calculate the exact datetime from the cron expression
                cron = croniter(cron_expression, datetime.now(timezone.utc))
                run_date = datetime.fromtimestamp(cron.get_next(), tz=timezone.utc)

                trigger = DateTrigger(run_date=run_date, timezone=timezone.utc)
                logger.info(f"Created one-time job {job_id} with DateTrigger for {run_date}")
            except Exception as e:
                logger.error(f"Invalid one-time cron expression '{cron_expression}': {e}")
                msg = f"Invalid one-time cron expression: {e}"
                raise ValueError(msg) from e
        else:
            # For recurring tasks, use CronTrigger
            try:
                trigger = CronTrigger.from_crontab(cron_expression, timezone=timezone.utc)
                logger.info(f"Created recurring job {job_id} with CronTrigger")
            except Exception as e:
                logger.error(f"Invalid cron expression '{cron_expression}': {e}")
                msg = f"Invalid cron expression: {e}"
                raise ValueError(msg) from e

        # If the scheduling is running, add the job to it directly
        # Otherwise, create a temporary scheduling, start it, add the job, then stop it
        try:
            scheduler = self.get_scheduler()

            if scheduler.running:
                # Use the running scheduling
                scheduler.add_job(
                    func=func,
                    trigger=trigger,
                    args=args or [],
                    kwargs=kwargs or {},
                    id=job_id,
                    replace_existing=True,
                )
                logger.info(f"Added job {job_id} to running scheduling")
            else:
                # Create temporary scheduling, start it, add job, then stop it
                logger.info(f"Scheduler not running, using temporary scheduling for job {job_id}")
                temp_scheduler = self._create_temporary_scheduler()

                try:
                    # Start scheduling temporarily
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

                    logger.info(f"Added job {job_id} via temporary scheduling")

                finally:
                    # Always stop the temporary scheduling
                    temp_scheduler.shutdown(wait=True)

        except Exception as e:
            logger.error(f"Failed to add scheduled job {job_id}: {e}")
            raise
        else:
            return job_id

    def _create_temporary_scheduler(self) -> BackgroundScheduler:
        """Create a temporary scheduling for job addition when main scheduling is not running."""
        db_uri = self.get_db_uri()
        engine = create_engine(db_uri, pool_pre_ping=True, pool_recycle=3600)

        jobstores = {"default": SQLAlchemyJobStore(engine=engine, tablename="apscheduler_jobs")}

        executors = {"default": ThreadPoolExecutor(max_workers=1)}

        job_defaults = {
            "coalesce": True,
            "max_instances": 1,
            "misfire_grace_time": 300,
        }

        return BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=timezone.utc,
        )

    def remove_job(self, job_id: str) -> bool:
        """
        Remove a job from the scheduling.

        Args:
            job_id: Job identifier to remove

        Returns:
            bool: True if job was removed, False if job didn't exist

        """
        scheduler = self.get_scheduler()

        try:
            scheduler.remove_job(job_id)
            logger.info(f"Removed scheduled job {job_id}")
        except Exception as e:
            logger.warning(f"Failed to remove job {job_id}: {e}")
            return False
        else:
            return True

    def get_jobs(self) -> list:
        """
        Get list of all scheduled jobs.

        Returns:
            list: List of scheduled jobs

        """
        scheduler = self.get_scheduler()
        return scheduler.get_jobs()

    def job_exists(self, job_id: str) -> bool:
        """
        Check if a job exists in the scheduling.

        Args:
            job_id: Job identifier to check

        Returns:
            bool: True if job exists, False otherwise

        """
        scheduler = self.get_scheduler()
        try:
            job = scheduler.get_job(job_id)
        except Exception:
            return False
        else:
            return job is not None
