"""
Delete Scheduled Tasks Tool for managing scheduled email tasks.

This tool allows users to delete scheduled tasks by providing the task ID.
It includes safety checks to ensure users can only delete their own tasks.
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import ClassVar, Optional

from pydantic import BaseModel, Field, field_validator
from smolagents import Tool
from sqlmodel import Session

from mxtoai._logging import get_logger
from mxtoai.crud import find_user_tasks_formatted, get_task_by_id, update_task_status
from mxtoai.db import init_db_connection
from mxtoai.models import TaskStatus
from mxtoai.request_context import RequestContext
from mxtoai.scheduling.scheduler import Scheduler

logger = get_logger("delete_scheduled_tasks_tool")


class DeleteTaskInput(BaseModel):
    """Input model for task deletion"""

    task_id: str = Field(..., description="Task ID to delete")

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v):
        """Validate that task_id is a valid UUID format"""
        try:
            uuid.UUID(v)
        except ValueError as e:
            msg = f"Invalid task ID format: {e}"
            raise ValueError(msg) from e
        return v


def extract_task_id_from_text(text: str) -> Optional[str]:
    """
    Extract UUID task ID from text content.

    Args:
        text: Text content to search for task ID

    Returns:
        Task ID if found, None otherwise

    """
    # UUID pattern - match standard UUID format
    uuid_pattern = r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
    matches = re.findall(uuid_pattern, text, re.IGNORECASE)

    if matches:
        return matches[0]  # Return first match
    return None


def find_user_tasks(db_session: Session, user_email: str, limit: int = 10) -> list[dict]:
    """
    Find tasks for a specific user.

    Args:
        user_email: Email address of the user
        db_session: Database session to use
        limit: Maximum number of tasks to return

    Returns:
        List of task dictionaries

    """
    try:
        return find_user_tasks_formatted(db_session, user_email, limit)
    except Exception as e:
        logger.error(f"Error finding user tasks: {e}")
        return []


class DeleteScheduledTasksTool(Tool):
    """
    Tool for deleting scheduled email tasks.

    This tool allows users to delete their own scheduled tasks by providing
    the task ID. It includes safety checks and proper cleanup.
    """

    name = "delete_scheduled_tasks"
    description = "Delete scheduled email tasks by task ID with user verification"
    inputs: ClassVar[dict] = {"task_id": {"type": "string", "description": "UUID of the task to delete"}}
    output_type = "object"

    def __init__(self, context: RequestContext):
        """
        Initialize the DeleteScheduledTasksTool with request context.

        Args:
            context: The request context containing email data

        """
        super().__init__()
        self.context = context
        # Create dedicated scheduling instance for this tool
        self.scheduler = Scheduler()

    def forward(self, task_id: str) -> dict:
        """
        Delete a scheduled task after verifying user ownership.

        Args:
            task_id: UUID of the task to delete

        Returns:
            Dictionary with deletion status and details

        """
        logger.info(f"Processing delete request for task {task_id}")

        try:
            # Validate input
            input_data = DeleteTaskInput(task_id=task_id)

            db_connection = init_db_connection()
            with db_connection.get_session() as session:
                # Find the task by ID using CRUD
                task = get_task_by_id(session, input_data.task_id)

                if not task:
                    logger.warning(f"Task {task_id} not found")
                    return {
                        "success": False,
                        "error": "Task not found",
                        "task_id": task_id,
                        "message": f"No task found with ID: {task_id}",
                    }

                # Check user ownership using email from the task's email_request
                task_email_request = task.email_request
                if isinstance(task_email_request, str):
                    try:
                        task_email_request = json.loads(task_email_request)
                    except json.JSONDecodeError:
                        logger.warning(f"Task {task_id} has corrupted JSON in email_request")
                        return {
                            "success": False,
                            "error": "Corrupted task data",
                            "task_id": task_id,
                            "message": "Task data is corrupted and cannot be processed",
                        }
                elif task_email_request is None:
                    logger.warning(f"Task {task_id} has null email_request")
                    return {
                        "success": False,
                        "error": "Corrupted task data",
                        "task_id": task_id,
                        "message": "Task data is corrupted and cannot be processed",
                    }

                # Support both 'from' and 'from_email' field names
                task_owner_email = (
                    task_email_request.get("from_email", "") or task_email_request.get("from", "")
                ).lower()
                requesting_email = self.context.email_request.from_email.lower()

                if task_owner_email != requesting_email:
                    logger.warning(
                        f"Permission denied: {requesting_email} cannot delete task owned by {task_owner_email}"
                    )
                    return {
                        "success": False,
                        "error": "Permission denied",
                        "task_id": task_id,
                        "message": f"You can only delete your own tasks. This task belongs to {task_owner_email}",
                    }

                # Remove from APScheduler if scheduler_job_id exists
                scheduler_removed = False
                scheduler_job_id = getattr(task, "scheduler_job_id", None)

                if scheduler_job_id:
                    try:
                        result = self.scheduler.remove_job(scheduler_job_id)
                        scheduler_removed = True
                        logger.info(f"Task {task_id} removed from scheduler: {result}")
                    except Exception as e:
                        logger.warning(f"Failed to remove task from scheduler: {e}")
                        # Continue with database cleanup even if scheduling fails
                else:
                    logger.info(f"Task {task_id} has no scheduler_job_id, skipping scheduler cleanup")

                    # Update task status to DELETED in database using CRUD
                update_task_status(session, task_id, TaskStatus.DELETED)

                logger.info(f"Task {task_id} successfully deleted")

                return {
                    "success": True,
                    "task_id": task_id,
                    "scheduler_removed": scheduler_removed,
                    "database_updated": True,
                    "message": "Task successfully deleted",
                    "deleted_at": datetime.now(timezone.utc).isoformat(),
                }

        except Exception as e:
            logger.error(f"Failed to delete task {task_id}: {e}")
            return {
                "success": False,
                "error": str(e),
                "task_id": task_id,
                "message": f"Failed to delete task: {e}",
            }
