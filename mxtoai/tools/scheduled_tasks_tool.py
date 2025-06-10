import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from croniter import croniter
from pydantic import BaseModel, Field, field_validator
from smolagents import Tool
from sqlmodel import select

from mxtoai._logging import get_logger
from mxtoai.db import init_db_connection
from mxtoai.models import Tasks, TaskStatus
from mxtoai.scheduled_task_executor import execute_scheduled_task
from mxtoai.scheduler import add_scheduled_job

logger = get_logger("scheduled_tasks_tool")

# Use synchronous DB connection
db_connection = init_db_connection()

# Remove automatic scheduler startup - scheduler will run as separate process
# try:
#     start_scheduler()
#     logger.info("APScheduler started successfully for scheduled tasks tool")
# except Exception as e:
#     logger.error(f"Failed to start APScheduler: {e}")


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
    email_request: dict[str, Any] = Field(..., description="Complete email request data to reprocess")
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

    @field_validator("email_request")
    @classmethod
    def validate_email_request(cls, v):
        """Validate that email_request contains necessary data"""
        # If input is a string, try to parse it as JSON
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except json.JSONDecodeError:
                msg = "email_request string must be valid JSON"
                raise ValueError(msg)

        if not isinstance(v, dict):
            msg = "email_request must be a dictionary or valid JSON string"
            raise ValueError(msg)

        # Normalize email request field keys (support both camelCase and lowercase)
        normalized_dict = {}
        for key, value in v.items():
            # Convert to lowercase for comparison
            key_lower = key.lower()

            # Map common variations to standard keys
            if key_lower in {"from", "from_email"}:
                normalized_dict["from"] = value
            elif key_lower == "to":
                normalized_dict["to"] = value
            elif key_lower == "subject":
                normalized_dict["subject"] = value
            elif key_lower in ["textcontent", "text_content"]:
                normalized_dict["textContent"] = value
            elif key_lower in ["htmlcontent", "html_content"]:
                normalized_dict["htmlContent"] = value
            else:
                # Keep original key for other fields
                normalized_dict[key] = value

        # Check for required fields using normalized keys
        required_fields = ["from", "to", "subject"]
        missing_fields = [field for field in required_fields if field not in normalized_dict]

        if missing_fields:
            msg = f"email_request missing required fields: {missing_fields}"
            raise ValueError(msg)

        return normalized_dict

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
        "email_request": {
            "type": "object",
            "description": "Complete email request data to reprocess"
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

    def forward(
        self,
        cron_expression: str,
        email_request: dict,
        task_description: str,
        next_run_time: Optional[str] = None,
    ) -> dict:
        """
        Sync implementation for creating a scheduled task with APScheduler integration.

        Args:
            cron_expression: Valid cron expression for task scheduling
            email_request: Complete email request data to reprocess
            task_description: Human-readable description of task
            next_run_time: Optional next run time in ISO 8601 format

        Returns:
            Dictionary with task details including task_id, next_execution, etc.

        """
        logger.info(f"Storing and scheduling task: {task_description}")

        # Check if this is already a scheduled task (prevent recursive scheduling)
        if email_request.get("scheduled_task_id"):
            logger.info(f"Skipping recursive scheduling for task {email_request.get('scheduled_task_id')}")
            return {
                "success": False,
                "error": "Recursive scheduling not allowed",
                "message": "This email is already being processed as a scheduled task",
                "existing_task_id": email_request.get("scheduled_task_id"),
            }

        try:
            # Validate input using Pydantic
            input_data = ScheduledTaskInput(
                cron_expression=cron_expression,
                email_request=email_request,
                task_description=task_description,
                next_run_time=next_run_time,
            )

            # Generate unique task ID
            task_id = str(uuid.uuid4())
            email_id = input_data.email_request.get("messageId") or f"scheduled-{task_id}"

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

            # Store task in database using ORM
            try:
                with db_connection.get_session() as session:
                    new_task = Tasks(
                        task_id=task_id,
                        email_id=email_id,
                        cron_expression=input_data.cron_expression,
                        email_request=input_data.email_request,
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


# Example usage for testing
if __name__ == "__main__":
    import os

    # Set required environment variables for testing
    if "DB_USER" not in os.environ:
        os.environ["DB_USER"] = "postgres"
        os.environ["DB_PASSWORD"] = "postgres"
        os.environ["DB_HOST"] = "localhost"
        os.environ["DB_PORT"] = "5432"
        os.environ["DB_NAME"] = "mxtoai"

    # Create tool instance
    tool = ScheduledTasksTool()

    # Example task
    sample_email_request = {
        "from": "test@example.com",
        "to": "remind@mxtoai.com",
        "subject": "Weekly Report Reminder",
        "textContent": "Remind me to review the weekly sales report",
        "emailId": "test_email_123",
    }

    # Execute the tool synchronously
    result = tool.forward(
        cron_expression="0 14 * * 1",  # Every Monday at 2 PM UTC
        email_request=sample_email_request,
        task_description="Weekly reminder to review sales report",
    )

