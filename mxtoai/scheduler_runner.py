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
from mxtoai.scheduler import reload_jobs_from_database, start_scheduler, stop_scheduler

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
        last_check = time.time()

        while True:
            current_time = time.time()

            # Check for new jobs periodically
            if current_time - last_check >= job_check_interval:
                check_for_new_jobs()
                last_check = current_time

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
