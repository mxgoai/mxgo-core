"""
Scheduled Task Executor for processing scheduled email tasks.

This module handles the execution of scheduled tasks by making HTTP requests
to the email processing endpoint with proper task tracking and status updates.
"""

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from mxtoai._logging import get_logger
from mxtoai.crud import (
    create_task_run,
    get_task_by_id,
    update_task_run_status,
    update_task_status,
)
from mxtoai.crud import (
    get_task_execution_status as crud_get_task_execution_status,
)
from mxtoai.db import init_db_connection
from mxtoai.models import TaskRunStatus, TaskStatus, is_active_status
from mxtoai.scheduling.scheduler import Scheduler, is_one_time_task

logger = get_logger("scheduled_task_executor")

# HTTP client configuration
HTTP_TIMEOUT = int(os.environ.get("SCHEDULER_API_TIMEOUT", "300"))  # 5 minutes
API_BASE_URL = os.environ.get("SCHEDULER_API_BASE_URL", "http://localhost:8000")


def execute_scheduled_task(task_id: str) -> None:
    """
    Execute a scheduled task by making an HTTP request to the /process-email endpoint.

    This function is called by APScheduler when a scheduled task should be executed.

    Args:
        task_id: UUID string of the task to execute

    Raises:
        Exception: If task execution fails

    """
    logger.info(f"Starting execution of scheduled task: {task_id}")

    # Initialize database connection
    db_connection = init_db_connection()
    task_run_id: Optional[str] = None

    try:
        # Read task from database
        with db_connection.get_session() as session:
            task = get_task_by_id(session, task_id)

            if not task:
                logger.error(f"Task {task_id} not found in database")
                msg = f"Task {task_id} not found"
                raise ValueError(msg)

            if not is_active_status(task.status):
                logger.warning(
                    f"Task {task_id} has terminal status {task.status}, removing from scheduler and skipping execution"
                )

                # Remove the job from scheduling since we're in the scheduling process
                if task.scheduler_job_id:
                    # Create a temporary scheduling instance to remove the job
                    temp_scheduler = Scheduler()
                    try:
                        temp_scheduler.remove_job(task.scheduler_job_id)
                        logger.info(f"Removed APScheduler job {task.scheduler_job_id} for terminal task {task_id}")

                        # Clear the scheduler_job_id to avoid future cleanup attempts
                        task.scheduler_job_id = None
                        session.add(task)
                        session.commit()

                    except Exception as e:
                        logger.warning(f"Failed to remove APScheduler job {task.scheduler_job_id}: {e}")

                return

            # Check start_time and expiry_time constraints
            current_time = datetime.now(timezone.utc)

            # Check if task has not reached its start time yet
            if task.start_time and current_time < task.start_time:
                logger.warning(
                    f"Task {task_id} has not reached its start time yet ({task.start_time}), skipping execution"
                )
                return

            # Check if task has expired
            if task.expiry_time and current_time > task.expiry_time:
                logger.warning(f"Task {task_id} has expired ({task.expiry_time}), marking as FINISHED")
                # Mark task as finished using CRUD
                update_task_status(session, task_id, TaskStatus.FINISHED)
                return

            # Update task status to EXECUTING using CRUD
            update_task_status(session, task_id, TaskStatus.EXECUTING, clear_email_data_if_terminal=False)

            # Create TaskRun entry using CRUD
            task_run_id = str(uuid.uuid4())
            create_task_run(session, task_run_id, task_id, TaskRunStatus.IN_PROGRESS)

            logger.info(f"Created TaskRun {task_run_id} for task {task_id}")

            # Parse email request data
            try:
                email_request = (
                    json.loads(task.email_request) if isinstance(task.email_request, str) else task.email_request
                )
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to parse email_request for task {task_id}: {e}")
                msg = f"Invalid email_request data: {e}"
                raise ValueError(msg) from e

            # Modify message ID for scheduled task execution to pass idempotency checks
            current_ts = datetime.now(timezone.utc).isoformat()

            # Generate a new unique message ID for this scheduled execution
            new_message_id = f"<scheduled-{task_id}-{current_ts}@mxtoai.com>"
            email_request["messageId"] = new_message_id
            logger.info(f"Modified message ID for scheduled task {task_id}: {new_message_id}")

        # Make HTTP request to process-email endpoint
        success = _make_process_email_request(task_id, email_request)

        # Update task and task run based on result
        with db_connection.get_session() as session:
            # Update TaskRun using CRUD
            new_run_status = TaskRunStatus.COMPLETED if success else TaskRunStatus.ERRORED
            update_task_run_status(session, task_run_id, new_run_status)

            # Update Task using CRUD
            task = get_task_by_id(session, task_id)
            if task:
                # For one-time tasks, mark as FINISHED after successful execution
                # For recurring tasks, mark as ACTIVE to continue scheduling
                if success:
                    # Check if this is a one-time task by examining cron expression
                    is_recurring = _is_recurring_cron_expression(task.cron_expression)
                    new_task_status = TaskStatus.ACTIVE if is_recurring else TaskStatus.FINISHED
                else:
                    new_task_status = TaskStatus.ACTIVE  # Keep active for retry

                update_task_status(session, task_id, new_task_status)

        if success:
            logger.info(f"Successfully executed scheduled task {task_id}")
        else:
            logger.error(f"Failed to execute scheduled task {task_id}")

    except Exception as e:
        logger.error(f"Error executing scheduled task {task_id}: {e}")

        # Update TaskRun as errored if it was created
        if task_run_id:
            try:
                with db_connection.get_session() as session:
                    # Update TaskRun using CRUD
                    update_task_run_status(session, task_run_id, TaskRunStatus.ERRORED)

                    # Update task status back to ACTIVE for potential retry using CRUD
                    update_task_status(session, task_id, TaskStatus.ACTIVE, clear_email_data_if_terminal=False)
            except Exception as cleanup_error:
                logger.error(f"Failed to update error status for task {task_id}: {cleanup_error}")

        raise


def _make_process_email_request(task_id: str, email_request: dict[str, Any]) -> bool:
    """
    Make HTTP POST request to /process-email endpoint.

    Args:
        task_id: The task ID being executed
        email_request: Email data to be processed

    Returns:
        bool: True if request was successful, False otherwise

    """
    try:
        # Prepare form data for /process-email endpoint
        form_data = {
            "scheduled_task_id": task_id,  # This indicates it's a scheduled task
        }

        # Map email_request fields to the expected form fields
        field_mapping = {
            "from_email": "from_email",
            "to": "to",
            "subject": "subject",
            "textContent": "textContent",
            "text_content": "textContent",
            "htmlContent": "htmlContent",
            "html_content": "htmlContent",
            "messageId": "messageId",
            "parent_message_id": "parent_message_id",
            "date": "date",
            "rawHeaders": "rawHeaders",
            "raw_headers": "rawHeaders",
        }

        # Map fields from email_request to form_data
        for request_field, form_field in field_mapping.items():
            if request_field in email_request:
                value = email_request[request_field]
                # Special handling for rawHeaders - convert dict to JSON string
                if (request_field in ["rawHeaders", "raw_headers"] and isinstance(value, dict)) or isinstance(
                    value, list | dict
                ):
                    form_data[form_field] = json.dumps(value)
                else:
                    form_data[form_field] = str(value)

        # Handle attachments if present (not as form field but as files)
        if email_request.get("../attachments"):
            # Note: For now, we're not handling file attachments in scheduled tasks
            # This would require additional logic to handle file content
            logger.warning(f"Task {task_id} has attachments but file handling not implemented for scheduled tasks")

        # Make HTTP request
        url = f"{API_BASE_URL}/process-email"

        # Get API key from environment
        api_key = os.environ.get("X_API_KEY")
        if not api_key:
            logger.error(f"X_API_KEY environment variable not set - cannot authenticate request for task {task_id}")
            return False

        headers = {"x-api-key": api_key}

        with httpx.Client(timeout=HTTP_TIMEOUT) as client:
            logger.info(f"Making HTTP request to {url} for task {task_id}")
            logger.debug(f"Form data keys: {list(form_data.keys())}")
            logger.debug(f"Form data: {form_data}")

            response = client.post(url, data=form_data, headers=headers)

            if response.status_code == 200:
                logger.info(f"HTTP request successful for task {task_id}")
                return True
            logger.error(f"HTTP request failed for task {task_id}: {response.status_code} - {response.text}")
            return False

    except httpx.TimeoutException:
        logger.error(f"HTTP request timed out for task {task_id}")
        return False
    except httpx.RequestError as e:
        logger.error(f"HTTP request error for task {task_id}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error making HTTP request for task {task_id}: {e}")
        return False


def _is_recurring_cron_expression(cron_expression: str) -> bool:
    """
    Determine if a cron expression represents a recurring schedule.

    Args:
        cron_expression: The cron expression to analyze

    Returns:
        bool: True if the expression represents a recurring schedule

    """
    # First validate that the cron expression is valid
    parts = cron_expression.strip().split()
    if len(parts) != 5:
        return False
    
    # Use the centralized is_one_time_task function and invert the result
    return not is_one_time_task(cron_expression)


def get_task_execution_status(task_id: str) -> Optional[dict[str, Any]]:
    """
    Get the current execution status of a task.

    Args:
        task_id: Task ID to check

    Returns:
        Dict with task status information or None if task not found

    """
    db_connection = init_db_connection()

    try:
        with db_connection.get_session() as session:
            return crud_get_task_execution_status(session, task_id)
    except Exception as e:
        logger.error(f"Error getting task execution status for {task_id}: {e}")
        return None
