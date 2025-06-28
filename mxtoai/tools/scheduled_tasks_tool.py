import uuid
from datetime import datetime, timedelta, timezone
from typing import ClassVar, Optional

from croniter import croniter
from pydantic import BaseModel, Field, field_validator
from smolagents import Tool

from mxtoai._logging import get_logger
from mxtoai.config import SCHEDULED_TASKS_MINIMUM_INTERVAL_HOURS
from mxtoai.crud import create_task, delete_task, update_task_status
from mxtoai.db import init_db_connection
from mxtoai.models import TaskStatus
from mxtoai.request_context import RequestContext
from mxtoai.scheduling.scheduled_task_executor import execute_scheduled_task
from mxtoai.scheduling.scheduler import Scheduler, is_one_time_task
from mxtoai.schemas import HandlerAlias
from mxtoai.utils import round_to_nearest_minute, validate_datetime_field

logger = get_logger("scheduled_tasks_tool")


def calculate_cron_interval(cron_expression: str) -> timedelta:  # noqa: PLR0912
    """
    Calculate the minimum interval between executions for a cron expression.

    Args:
        cron_expression: The cron expression to analyze

    Returns:
        timedelta: The minimum interval between executions

    Raises:
        ValueError: If cron expression is invalid or interval cannot be determined

    """
    try:
        # Parse the cron expression
        parts = cron_expression.strip().split()
        cron_parts_count = 5
        if len(parts) != cron_parts_count:
            msg = "Cron expression must have exactly 5 parts"
            raise ValueError(msg)

        minute, hour, day, month, weekday = parts
        interval = None

        # Check for every minute execution (* in minute field)
        if minute == "*":
            interval = timedelta(minutes=1)
        # Check for specific minute intervals (*/n in minute field)
        elif minute.startswith("*/"):
            interval_minutes = int(minute[2:])
            interval = timedelta(minutes=interval_minutes)
        # Check for minute ranges or lists
        elif "," in minute or "-" in minute:
            # For complex minute patterns, assume worst case of every minute
            interval = timedelta(minutes=1)
        # Check for every hour execution (* in hour field with specific minute)
        elif hour == "*":
            interval = timedelta(hours=1)
        # Check for specific hour intervals (*/n in hour field)
        elif hour.startswith("*/"):
            interval_hours = int(hour[2:])
            interval = timedelta(hours=interval_hours)
        # Check for hour ranges or lists
        elif "," in hour or "-" in hour:
            # For complex hour patterns, assume worst case of every hour
            interval = timedelta(hours=1)
        # If we get here, it's likely a daily, weekly, monthly, or yearly pattern
        # Daily pattern (specific hour and minute, every day)
        elif day == "*" and month == "*" and (weekday in {"*", "?"}):
            interval = timedelta(days=1)
        # Weekly pattern (specific weekday)
        elif day == "*" and month == "*" and weekday not in {"*", "?"}:
            interval = timedelta(weeks=1)
        # Monthly pattern (specific day of month)
        elif day != "*" and month == "*":
            interval = timedelta(days=30)  # Approximate monthly interval
        # Yearly pattern (specific month and day)
        elif day != "*" and month != "*":
            interval = timedelta(days=365)  # Yearly interval
        else:
            # Default to daily if we can't determine the pattern
            interval = timedelta(days=1)

    except Exception as e:
        msg = f"Could not calculate interval for cron expression '{cron_expression}': {e}"
        raise ValueError(msg) from e
    else:
        return interval


def validate_minimum_interval(cron_expression: str) -> None:
    """
    Validate that a recurring cron expression has a minimum interval of 1 hour.
    One-time tasks are exempt from this validation.

    Args:
        cron_expression: The cron expression to validate

    Raises:
        ValueError: If the interval is less than 1 hour for recurring tasks

    """
    # Skip validation for one-time tasks
    if is_one_time_task(cron_expression):
        return

    interval = calculate_cron_interval(cron_expression)
    minimum_interval = timedelta(hours=SCHEDULED_TASKS_MINIMUM_INTERVAL_HOURS)

    if interval < minimum_interval:
        msg = (
            f"Recurring task interval is too frequent. "
            f"Found interval: {interval}, minimum required: {minimum_interval}. "
            f"Please use a cron expression that runs at most once per hour."
        )
        raise ValueError(msg)


class ScheduledTaskInput(BaseModel):
    """Input model for scheduled task creation"""

    cron_expression: str = Field(..., description="Valid cron expression for task scheduling")
    distilled_future_task_instructions: str = Field(
        ..., description="Distilled and detailed instructions about how the task will be processed in future"
    )
    start_time: Optional[str] = Field(
        None, description="Start time for the task - task will not execute before this time (ISO format)"
    )
    end_time: Optional[str] = Field(
        None, description="End time for the task - task will not execute after this time (ISO format)"
    )

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v):
        """Validate that the cron expression is valid and meets minimum interval requirements"""
        try:
            # Test if cron expression is valid
            cron = croniter(v, datetime.now(timezone.utc))

            # Check if this is a one-time task in the past
            if is_one_time_task(v):
                next_run = datetime.fromtimestamp(cron.get_next(), tz=timezone.utc)
                if next_run < datetime.now(timezone.utc):
                    msg = f"One-time task scheduled for the past: {next_run}"
                    raise ValueError(msg)

            # Validate minimum interval for recurring tasks
            validate_minimum_interval(v)

        except Exception as e:
            msg = f"Invalid cron expression: {e}"
            raise ValueError(msg) from e
        return v

    @field_validator("start_time")
    @classmethod
    def validate_start_time(cls, v):
        """Validate that start_time is a valid ISO 8601 datetime string if provided"""
        return validate_datetime_field(v, "start_time")

    @field_validator("end_time")
    @classmethod
    def validate_end_time(cls, v):
        """Validate that end_time is a valid ISO 8601 datetime string if provided"""
        return validate_datetime_field(v, "end_time")


class ScheduledTasksTool(Tool):
    """
    Tool for creating and managing scheduled email tasks.

    This tool allows users to schedule emails to be processed at specific times
    using cron expressions. The tool integrates with APScheduler for robust scheduling.
    """

    name: ClassVar[str] = "scheduled_tasks"
    description: ClassVar[str] = "Create, schedule, and manage future email processing tasks using cron expressions"
    inputs: ClassVar[dict] = {
        "cron_expression": {"type": "string", "description": "Valid cron expression for task scheduling"},
        "distilled_future_task_instructions": {
            "type": "string",
            "description": "Distilled and detailed instructions about how the task will be processed in future",
        },
        "start_time": {
            "type": "string",
            "description": "Optional start time for the task in ISO 8601 format - task will not execute before this time",
            "nullable": True,
        },
        "end_time": {
            "type": "string",
            "description": "Optional end time for the task in ISO 8601 format - task will not execute after this time",
            "nullable": True,
        },
    }
    output_type: ClassVar[str] = "object"

    def __init__(self, context: RequestContext):
        """
        Initialize the ScheduledTasksTool with request context.

        Args:
            context: The request context containing email data

        """
        super().__init__()
        self.context = context
        # Create dedicated scheduling instance for this tool
        self.scheduler = Scheduler()

    def forward(
        self,
        cron_expression: str,
        distilled_future_task_instructions: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> dict:
        """
        Sync implementation for creating a scheduled task with APScheduler integration.

        Args:
            cron_expression: Valid cron expression for task scheduling
            distilled_future_task_instructions: Distilled and detailed instructions about how the task will be processed in future
            start_time: Optional start time for the task in ISO 8601 format
            end_time: Optional end time for the task in ISO 8601 format

        Returns:
            Dictionary with task details including task_id, next_execution, etc.

        """
        logger.info(f"Storing and scheduling task: {distilled_future_task_instructions}")
        logger.info(f"Cron expression: {cron_expression}")
        logger.info(f"Is one-time task: {is_one_time_task(cron_expression) if cron_expression else 'Unknown'}")

        # Get email request from context
        email_request = self.context.email_request

        # Check if this is already a scheduled task (prevent recursive scheduling)
        if email_request.scheduled_task_id:
            logger.info(f"Skipping recursive scheduling for task {email_request.scheduled_task_id}")
            return {
                "success": False,
                "error": "Recursive scheduling not allowed",
                "message": "This email is already being processed as a scheduled task",
                "existing_task_id": email_request.scheduled_task_id,
            }

        try:
            # Validate input using Pydantic
            input_data = ScheduledTaskInput(
                cron_expression=cron_expression,
                distilled_future_task_instructions=distilled_future_task_instructions,
                start_time=start_time,
                end_time=end_time,
            )

            # Additional validation for potentially incorrect cron expressions
            if is_one_time_task(cron_expression):
                cron_iter = croniter(cron_expression, datetime.now(timezone.utc))
                next_execution_time = datetime.fromtimestamp(cron_iter.get_next(), tz=timezone.utc)
                time_until_execution = next_execution_time - datetime.now(timezone.utc)
                logger.info(f"One-time task will execute at: {next_execution_time} (in {time_until_execution})")

            db_connection = init_db_connection()
            # Generate unique task ID
            task_id = str(uuid.uuid4())
            email_id = email_request.from_email

            # Parse start_time and end_time if provided
            parsed_start_time = None
            parsed_end_time = None

            if input_data.start_time:
                try:
                    parsed_start_time = datetime.fromisoformat(input_data.start_time.replace("Z", "+00:00"))
                    parsed_start_time = round_to_nearest_minute(parsed_start_time)
                except Exception as e:
                    logger.warning(f"Could not parse start_time: {e}")

            if input_data.end_time:
                try:
                    parsed_end_time = datetime.fromisoformat(input_data.end_time.replace("Z", "+00:00"))
                    parsed_end_time = round_to_nearest_minute(parsed_end_time)
                except Exception as e:
                    logger.warning(f"Could not parse end_time: {e}")

            # Validate that start_time is before end_time if both are provided
            if parsed_start_time and parsed_end_time and parsed_start_time >= parsed_end_time:
                return {
                    "success": False,
                    "error": "Invalid time range",
                    "message": "start_time must be before end_time",
                    "task_description": distilled_future_task_instructions,
                }

            # Calculate next execution time from cron expression
            cron_iter = croniter(input_data.cron_expression, datetime.now(timezone.utc))
            next_execution = round_to_nearest_minute(datetime.fromtimestamp(cron_iter.get_next(), tz=timezone.utc))

            # Create scheduling job ID (APScheduler will use this)
            scheduler_job_id = f"task_{task_id}"

            # Save distilled instructions and task description to email request
            email_request.distilled_processing_instructions = input_data.distilled_future_task_instructions
            email_request.task_description = distilled_future_task_instructions
            # TODO: Need an AI driver logic here but for now we'll just redirect to ask
            email_request.distilled_alias = HandlerAlias.ASK
            email_request.parent_message_id = email_request.messageId

            # Store task in database using CRUD
            try:
                with db_connection.get_session() as session:
                    create_task(
                        session=session,
                        task_id=task_id,
                        email_id=email_id,
                        cron_expression=input_data.cron_expression,
                        email_request=email_request.model_dump(),
                        scheduler_job_id=scheduler_job_id,
                        start_time=parsed_start_time,
                        expiry_time=parsed_end_time,
                        status=TaskStatus.INITIALISED,
                    )
                    logger.info(f"Task successfully stored with CRUD method, ID: {task_id}")

            except Exception as crud_error:
                logger.error(f"CRUD method failed: {crud_error}")
                raise

            # Schedule the task with APScheduler
            try:
                self.scheduler.add_job(
                    job_id=scheduler_job_id,
                    cron_expression=input_data.cron_expression,
                    func=execute_scheduled_task,
                    args=[task_id],
                )
                logger.info(f"Task {task_id} scheduled successfully with job ID: {scheduler_job_id}")

                # Update task status to ACTIVE in database using CRUD
                with db_connection.get_session() as session:
                    update_task_status(session, task_id, TaskStatus.ACTIVE, clear_email_data_if_terminal=False)

            except Exception as scheduler_error:
                logger.error(f"Failed to schedule task {task_id}: {scheduler_error}")
                # Mark task as failed in database using CRUD
                try:
                    with db_connection.get_session() as session:
                        delete_task(session, task_id)
                except Exception as cleanup_error:
                    logger.warning(f"Failed to cleanup task {task_id} after scheduler error: {cleanup_error}")
                raise scheduler_error

            # Return success response
            return {
                "success": True,
                "task_id": task_id,
                "scheduler_job_id": scheduler_job_id,
                "cron_expression": input_data.cron_expression,
                "next_execution": next_execution.isoformat() if next_execution else None,
                "start_time": parsed_start_time.isoformat() if parsed_start_time else None,
                "end_time": parsed_end_time.isoformat() if parsed_end_time else None,
                "task_description": distilled_future_task_instructions,
                "message": f"Task '{distilled_future_task_instructions}' scheduled successfully",
            }

        except Exception as e:
            logger.error(f"Failed to create scheduled task: {e}")
            return {
                "success": False,
                "error": str(e),
                "task_description": distilled_future_task_instructions,
                "message": f"Failed to schedule task: {e}",
            }
