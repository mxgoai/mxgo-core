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
from mxtoai.db import init_db_connection
from mxtoai.models import TERMINAL_TASK_STATUSES, Tasks
from mxtoai.scheduler import get_scheduler, reload_jobs_from_database, start_scheduler, stop_scheduler

logger = get_logger("scheduler_runner")


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("Received shutdown signal, stopping scheduler...")
    stop_scheduler()
    sys.exit(0)


def check_for_new_jobs():
    """
    Check for new jobs that may have been added by other processes.
    """
    try:
        new_jobs_count = reload_jobs_from_database()
        if new_jobs_count > 0:
            logger.info(f"Loaded {new_jobs_count} new jobs from database")

    except Exception as e:
        logger.warning(f"Error checking for new jobs: {e}")


def cleanup_terminal_task_jobs():
    """
    Remove APScheduler jobs for tasks that have reached terminal status.
    This handles cases where tasks were marked as terminal by other processes.
    """
    try:
        db_connection = init_db_connection()
        scheduler = get_scheduler()

        if not scheduler.running:
            return

        with db_connection.get_session() as session:
            from sqlmodel import select

            # Find terminal tasks that still have scheduler_job_id
            statement = (
                select(Tasks)
                .where(Tasks.status.in_(TERMINAL_TASK_STATUSES))
                .where(Tasks.scheduler_job_id.is_not(None))
            )
            terminal_tasks = session.exec(statement).all()

            cleaned_count = 0
            for task in terminal_tasks:
                try:
                    scheduler.remove_job(task.scheduler_job_id)
                    logger.info(f"Cleaned up APScheduler job {task.scheduler_job_id} for terminal task {task.task_id} (status: {task.status})")

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


def main():
    """Main entry point for standalone scheduler process."""
    # Handle shutdown gracefully
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("Starting standalone APScheduler process...")

    try:
        start_scheduler()
        logger.info("APScheduler started successfully, ready to execute scheduled tasks")

        # Keep the process alive and periodically check for new jobs
        job_check_interval = 10  # Check every 10 seconds for faster responsiveness
        cleanup_interval = 60  # Cleanup every 60 seconds
        last_check = time.time()
        last_cleanup = time.time()

        while True:
            current_time = time.time()

            # Check for new jobs periodically
            if current_time - last_check >= job_check_interval:
                check_for_new_jobs()
                last_check = current_time

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
        logger.info("Shutting down scheduler...")
        stop_scheduler()


if __name__ == "__main__":
    main()
