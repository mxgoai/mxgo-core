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
from sqlmodel import select

from mxtoai._logging import get_logger
from mxtoai.db import init_db_connection
from mxtoai.models import TaskRun, TaskRunStatus, Tasks, TaskStatus

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
            statement = select(Tasks).where(Tasks.task_id == task_id)
            task = session.exec(statement).first()

            if not task:
                logger.error(f"Task {task_id} not found in database")
                msg = f"Task {task_id} not found"
                raise ValueError(msg)

            if task.status == TaskStatus.DELETED:
                logger.warning(f"Task {task_id} is marked as deleted, skipping execution")
                return

            # Update task status to EXECUTING
            task.status = TaskStatus.EXECUTING
            task.updated_at = datetime.now(timezone.utc)
            session.add(task)

            # Create TaskRun entry
            task_run_id = str(uuid.uuid4())
            task_run = TaskRun(
                run_id=task_run_id,
                task_id=task_id,
                status=TaskRunStatus.IN_PROGRESS,
            )
            session.add(task_run)
            session.commit()

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

        # Make HTTP request to process-email endpoint
        success = _make_process_email_request(task_id, email_request)

        # Update task and task run based on result
        with db_connection.get_session() as session:
            # Update TaskRun
            statement = select(TaskRun).where(TaskRun.run_id == task_run_id)
            task_run = session.exec(statement).first()
            if task_run:
                task_run.status = TaskRunStatus.COMPLETED if success else TaskRunStatus.ERRORED
                task_run.updated_at = datetime.now(timezone.utc)
                session.add(task_run)

            # Update Task
            statement = select(Tasks).where(Tasks.task_id == task_id)
            task = session.exec(statement).first()
            if task:
                # For one-time tasks, mark as FINISHED after successful execution
                # For recurring tasks, mark as ACTIVE to continue scheduling
                if success:
                    # Check if this is a one-time task by examining cron expression
                    is_recurring = _is_recurring_cron_expression(task.cron_expression)
                    task.status = TaskStatus.ACTIVE if is_recurring else TaskStatus.FINISHED
                else:
                    task.status = TaskStatus.ACTIVE  # Keep active for retry

                task.updated_at = datetime.now(timezone.utc)
                session.add(task)

            session.commit()

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
                    statement = select(TaskRun).where(TaskRun.run_id == task_run_id)
                    task_run = session.exec(statement).first()
                    if task_run:
                        task_run.status = TaskRunStatus.ERRORED
                        task_run.updated_at = datetime.now(timezone.utc)
                        session.add(task_run)

                    # Update task status back to ACTIVE for potential retry
                    statement = select(Tasks).where(Tasks.task_id == task_id)
                    task = session.exec(statement).first()
                    if task:
                        task.status = TaskStatus.ACTIVE
                        task.updated_at = datetime.now(timezone.utc)
                        session.add(task)

                    session.commit()
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
            "from": "from_email",  # Handle both variations
            "to": "to",
            "subject": "subject",
            "textContent": "textContent",
            "text_content": "textContent",
            "htmlContent": "htmlContent",
            "html_content": "htmlContent",
            "messageId": "messageId",
            "message_id": "messageId",
            "date": "date",
            "emailId": "emailId",
            "email_id": "emailId",
            "rawHeaders": "rawHeaders",
            "raw_headers": "rawHeaders",
        }

        # Map fields from email_request to form_data
        for request_field, form_field in field_mapping.items():
            if request_field in email_request:
                value = email_request[request_field]
                # Special handling for rawHeaders - convert dict to JSON string
                if (request_field in ["rawHeaders", "raw_headers"] and isinstance(value, dict)) or isinstance(value, list | dict):
                    form_data[form_field] = json.dumps(value)
                else:
                    form_data[form_field] = str(value)

        # Handle attachments if present (not as form field but as files)
        if email_request.get("attachments"):
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
    # This is a simple heuristic - in practice, most cron expressions are recurring
    # unless they specify a specific date in the past or use specific date patterns

    # Split cron expression into parts
    parts = cron_expression.strip().split()

    if len(parts) != 5:
        # Invalid cron expression format, assume non-recurring for safety
        return False

    minute, hour, day, month, dayofweek = parts

    # Check for specific date patterns that might be one-time
    # If day and month are both specific numbers (not wildcards), it might be one-time
    if (
        day.isdigit()
        and month.isdigit()
        and dayofweek == "*"
        and not any(char in cron_expression for char in ["/", "-", ","])
    ):
        # This looks like a specific date, might be one-time
        # But we'll default to recurring for safety
        return True

    # Most other patterns are recurring
    return True


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
            # Get task info
            statement = select(Tasks).where(Tasks.task_id == task_id)
            task = session.exec(statement).first()

            if not task:
                return None

            # Get latest task run
            statement = select(TaskRun).where(TaskRun.task_id == task_id).order_by(TaskRun.created_at.desc())
            latest_run = session.exec(statement).first()

            result = {
                "task_id": task_id,
                "task_status": task.status,
                "created_at": task.created_at,
                "updated_at": task.updated_at,
                "cron_expression": task.cron_expression,
                "scheduler_job_id": task.scheduler_job_id,
            }

            if latest_run:
                result["latest_run"] = {
                    "run_id": latest_run.run_id,
                    "status": latest_run.status,
                    "created_at": latest_run.created_at,
                    "updated_at": latest_run.updated_at,
                }

            return result

    except Exception as e:
        logger.error(f"Error getting task execution status for {task_id}: {e}")
        return None
