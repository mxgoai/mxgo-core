#!/usr/bin/env python3
"""
Standalone APScheduler process runner.
This runs independently from Dramatiq workers and API server.
Reads jobs from PostgreSQL jobstore and executes them via REST API calls.
"""

import signal
import sys
import time

from mxtoai._logging import get_logger
from mxtoai.crud import get_tasks_by_status
from mxtoai.db import init_db_connection
from mxtoai.models import TERMINAL_TASK_STATUSES
from mxtoai.scheduling.scheduler import Scheduler

logger = get_logger("scheduler_runner")

# Create dedicated scheduling instance for this process
scheduler_instance = Scheduler()


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Received shutdown signal, stopping scheduling...")
    scheduler_instance.stop()
    sys.exit(0)


def cleanup_terminal_task_jobs():
    """
    Remove APScheduler jobs for tasks that have reached terminal status.
    This handles cases where tasks were marked as terminal by other processes.
    """
    try:
        db_connection = init_db_connection()

        if not scheduler_instance.is_running():
            return

        with db_connection.get_session() as session:
            # Find terminal tasks that still have scheduler_job_id using CRUD
            terminal_tasks = get_tasks_by_status(session, TERMINAL_TASK_STATUSES, has_scheduler_job_id=True)

            cleaned_count = 0
            for task in terminal_tasks:
                try:
                    scheduler_instance.remove_job(task.scheduler_job_id)
                    logger.info(
                        f"Cleaned up APScheduler job {task.scheduler_job_id} for terminal task {task.task_id} (status: {task.status})"
                    )

                    # Clear the scheduler_job_id to avoid future cleanup attempts
                    task.scheduler_job_id = None
                    session.add(task)
                    cleaned_count += 1

                except Exception as e:
                    logger.warning(f"Failed to remove job {task.scheduler_job_id} for task {task.task_id}: {e}")

            if cleaned_count > 0:
                session.commit()
                logger.info(f"Cleaned up {cleaned_count} terminal task jobs from APScheduler")

    except Exception as e:
        logger.error(f"Error during terminal task cleanup: {e}")


def refresh_jobs_from_database():
    """
    Refresh the scheduling's job list from the PostgreSQL jobstore.
    This ensures the scheduling picks up new jobs added by other processes.
    """
    try:
        scheduler_instance.refresh_jobs()
    except Exception as e:
        logger.error(f"Error refreshing jobs from database: {e}")


def main():
    """Main entry point for standalone scheduling process."""
    # Handle shutdown gracefully
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Starting standalone APScheduler process...")

    try:
        scheduler_instance.start()
        logger.info("APScheduler started successfully, ready to execute scheduled tasks")

        # Keep the process alive and periodically check for new jobs
        job_refresh_interval = 10  # Refresh jobs every 30 seconds
        cleanup_interval = 60  # Cleanup every 60 seconds
        last_refresh = time.time()
        last_cleanup = time.time()

        while True:
            current_time = time.time()

            # Refresh jobs from database periodically
            if current_time - last_refresh >= job_refresh_interval:
                refresh_jobs_from_database()
                last_refresh = current_time

            # Cleanup terminal task jobs periodically
            if current_time - last_cleanup >= cleanup_interval:
                cleanup_terminal_task_jobs()
                last_cleanup = current_time

            time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Scheduler process interrupted by user")
    except Exception as e:
        logger.error(f"Scheduler process error: {e}")
        raise
    finally:
        logger.info("Shutting down scheduling...")
        scheduler_instance.stop()


if __name__ == "__main__":
    main()
