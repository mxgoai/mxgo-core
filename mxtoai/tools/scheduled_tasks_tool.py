import uuid
from datetime import datetime, timezone
from typing import Optional

from croniter import croniter
from pydantic import BaseModel, Field, field_validator
from smolagents import Tool
from sqlmodel import select

from mxtoai._logging import get_logger
from mxtoai.db import init_db_connection
from mxtoai.models import Tasks, TaskStatus
from mxtoai.scheduled_task_executor import execute_scheduled_task
from mxtoai.scheduler import add_scheduled_job
from mxtoai.schemas import EmailRequest, HandlerAlias

logger = get_logger("scheduled_tasks_tool")

# Use synchronous DB connection
db_connection = init_db_connection()


def round_to_nearest_minute(dt: datetime) -> datetime:
    """
    Round a datetime object to the nearest minute.
    This ensures we don't use seconds in cron expressions,
    as most cron implementations only support minute-level precision.

    Args:
        dt: The datetime to round

    Returns:
        A datetime object rounded to the nearest minute

    """
    if dt.second:
        # Add one minute and set seconds/microseconds to 0
        return dt.replace(second=0, microsecond=0)
    # Already at minute precision, just remove microseconds if any
    return dt.replace(second=0, microsecond=0)


class ScheduledTaskInput(BaseModel):
    """Input model for scheduled task creation"""

    cron_expression: str = Field(..., description="Valid cron expression for task scheduling")
    distilled_future_task_instructions: str = Field(..., description="Distilled and detailed instructions about how the task will be processed in future")
    task_description: str = Field(..., description="Human-readable description of the task")
    next_run_time: Optional[str] = Field(None, description="Next execution time (ISO format)")

    @field_validator("cron_expression")
    @classmethod
    def validate_cron_expression(cls, v):
        """Validate that the cron expression is valid"""
        try:
            # Test if cron expression is valid
            croniter(v)
        except Exception as e:
            msg = f"Invalid cron expression: {e}"
            raise ValueError(msg) from e
        return v

    @field_validator("next_run_time")
    @classmethod
    def validate_next_run_time(cls, v):
        """Validate that next_run_time is a valid ISO 8601 datetime string if provided"""
        if v is None:
            return v
        try:
            # Parse the datetime string and ensure it has a timezone
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            # Round to the nearest minute
            dt = round_to_nearest_minute(dt)

            # Return the rounded datetime as an ISO string
            return dt.isoformat()
        except ValueError as e:
            msg = f"Invalid datetime format for next_run_time: {e}"
            raise ValueError(msg)
        return v


class ScheduledTasksTool(Tool):
    """
    Tool for creating and managing scheduled email tasks.

    This tool allows users to schedule emails to be processed at specific times
    using cron expressions. The tool integrates with APScheduler for robust scheduling.
    """

    name = "scheduled_tasks"
    description = "Create, schedule, and manage future email processing tasks using cron expressions"
    inputs = {
        "cron_expression": {
            "type": "string",
            "description": "Valid cron expression for task scheduling"
        },
        "distilled_future_task_instructions": {
            "type": "string",
            "description": "Distilled and detailed instructions about how the task will be processed in future"
        },
        "task_description": {
            "type": "string",
            "description": "Human-readable description of the task"
        },
        "next_run_time": {
            "type": "string",
            "description": "Optional next run time in ISO 8601 format",
            "nullable": True
        }
    }
    output_type = "object"

    def __init__(self, email_request: EmailRequest):
        """
        Initialize the ScheduledTasksTool with an optional email request.

        Args:
            email_request: Optional email request data to reprocess

        """
        super().__init__()
        self.email_request = email_request

    def forward(
        self,
        cron_expression: str,
        distilled_future_task_instructions: str,
        task_description: str,
        next_run_time: Optional[str] = None,
    ) -> dict:
        """
        Sync implementation for creating a scheduled task with APScheduler integration.

        Args:
            cron_expression: Valid cron expression for task scheduling
            distilled_future_task_instructions: Distilled and detailed instructions about how the task will be processed in future
            task_description: Human-readable description of task
            next_run_time: Optional next run time in ISO 8601 format

        Returns:
            Dictionary with task details including task_id, next_execution, etc.

        """
        logger.info(f"Storing and scheduling task: {task_description}")

        # Check if this is already a scheduled task (prevent recursive scheduling)
        if self.email_request.scheduled_task_id:
            logger.info(f"Skipping recursive scheduling for task {self.email_request.scheduled_task_id}")
            return {
                "success": False,
                "error": "Recursive scheduling not allowed",
                "message": "This email is already being processed as a scheduled task",
                "existing_task_id": self.email_request.scheduled_task_id,
            }

        try:
            # Validate input using Pydantic
            input_data = ScheduledTaskInput(
                cron_expression=cron_expression,
                distilled_future_task_instructions=distilled_future_task_instructions,
                task_description=task_description,
                next_run_time=next_run_time,
            )

            # Generate unique task ID
            task_id = str(uuid.uuid4())
            email_id = self.email_request.from_email

            # Round the next execution time to nearest minute if provided
            next_execution = None
            if next_run_time:
                try:
                    parsed_time = datetime.fromisoformat(next_run_time.replace("Z", "+00:00"))
                    next_execution = round_to_nearest_minute(parsed_time)
                except Exception as e:
                    logger.warning(f"Could not parse next_run_time: {e}")

            # Calculate next execution time from cron if not provided
            if not next_execution:
                cron_iter = croniter(input_data.cron_expression, datetime.now(timezone.utc))
                next_execution = round_to_nearest_minute(datetime.fromtimestamp(cron_iter.get_next(), tz=timezone.utc))

            # Create scheduler job ID (APScheduler will use this)
            scheduler_job_id = f"task_{task_id}"

            # Save distilled instructions to email request
            self.email_request.distilled_processing_instructions = input_data.distilled_future_task_instructions
            # TODO: Need an AI driver logic here but for now we'll just redirect to ask
            self.email_request.distilled_alias = HandlerAlias.ASK

            # Store task in database using ORM
            try:
                with db_connection.get_session() as session:
                    new_task = Tasks(
                        task_id=task_id,
                        email_id=email_id,
                        cron_expression=input_data.cron_expression,
                        email_request=self.email_request.model_dump(),
                        scheduler_job_id=scheduler_job_id,
                        status=TaskStatus.INITIALISED,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )

                    session.add(new_task)
                    session.commit()
                    logger.info(f"Task successfully stored with ORM method, ID: {task_id}")

            except Exception as orm_error:
                logger.error(f"ORM method failed: {orm_error}")
                raise

            # Schedule the task with APScheduler
            try:
                add_scheduled_job(
                    job_id=scheduler_job_id,
                    cron_expression=input_data.cron_expression,
                    func=execute_scheduled_task,
                    args=[task_id],
                )
                logger.info(f"Task {task_id} scheduled successfully with job ID: {scheduler_job_id}")

                # Update task status to ACTIVE in database using ORM
                with db_connection.get_session() as session:
                    statement = select(Tasks).where(Tasks.task_id == task_id)
                    task = session.exec(statement).first()
                    if task:
                        task.status = TaskStatus.ACTIVE
                        task.updated_at = datetime.now(timezone.utc)
                        session.add(task)
                        session.commit()

            except Exception as scheduler_error:
                logger.error(f"Failed to schedule task {task_id}: {scheduler_error}")
                # Mark task as failed in database using ORM
                try:
                    with db_connection.get_session() as session:
                        statement = select(Tasks).where(Tasks.task_id == task_id)
                        task = session.exec(statement).first()
                        if task:
                            session.delete(task)
                            session.commit()
                except Exception:
                    pass  # Ignore cleanup errors
                raise scheduler_error

            # Return success response
            return {
                "success": True,
                "task_id": task_id,
                "scheduler_job_id": scheduler_job_id,
                "cron_expression": input_data.cron_expression,
                "next_execution": next_execution.isoformat() if next_execution else None,
                "task_description": task_description,
                "message": f"Task '{task_description}' scheduled successfully",
            }

        except Exception as e:
            logger.error(f"Failed to create scheduled task: {e}")
            return {
                "success": False,
                "error": str(e),
                "task_description": task_description,
                "message": f"Failed to schedule task: {e}",
            }
