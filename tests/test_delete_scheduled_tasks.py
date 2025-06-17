"""
Tests for the delete scheduled tasks tool and functionality.
"""

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from mxtoai.db import init_db_connection
from mxtoai.models import Tasks, TaskStatus
from mxtoai.schemas import EmailRequest
from mxtoai.tools.delete_scheduled_tasks_tool import (
    DeleteScheduledTasksTool,
    DeleteTaskInput,
    extract_task_id_from_text,
    find_user_tasks,
)

# Check if database is available for testing
DATABASE_AVAILABLE = bool(os.environ.get("TEST_DB_URL"))

def requires_database(func):
    """Decorator to skip tests that require database when database is not available."""
    return pytest.mark.skipif(not DATABASE_AVAILABLE, reason="Database not available for testing")(func)

class TestDeleteTaskInput:
    """Test the input validation for delete task requests."""

    def test_valid_input(self):
        """Test valid task deletion input."""
        task_id = str(uuid.uuid4())
        input_data = DeleteTaskInput(
            task_id=task_id,
        )
        assert str(input_data.task_id) == task_id

    def test_invalid_task_id_format(self):
        """Test validation fails for invalid UUID format."""
        with pytest.raises(ValidationError) as exc_info:
            DeleteTaskInput(
                task_id="not-a-uuid",
            )
        assert "Invalid task ID format" in str(exc_info.value)

    def test_missing_user_email(self):
        """Test validation fails for missing user email."""
        str(uuid.uuid4())
        # No user_email field, so this test is not needed anymore


class TestExtractTaskId:
    """Test task ID extraction functionality."""

    def test_extract_uuid_from_text(self):
        """Test extracting UUID from text content."""
        task_id = "12345678-1234-1234-1234-123456789012"
        text = f"Please delete task {task_id} from my schedule."

        extracted = extract_task_id_from_text(text)
        assert extracted == task_id

    def test_extract_task_id_with_label(self):
        """Test extracting task ID with label prefix."""
        task_id = "abcdef01-1234-5678-9abc-123456789012"  # Use valid hex characters
        text = f"Task ID: {task_id} should be removed"

        extracted = extract_task_id_from_text(text)
        assert extracted == task_id

    def test_extract_first_uuid_when_multiple(self):
        """Test that first UUID is returned when multiple exist."""
        task_id1 = "11111111-1111-1111-1111-111111111111"
        task_id2 = "22222222-2222-2222-2222-222222222222"
        text = f"Delete {task_id1} and also {task_id2}"

        extracted = extract_task_id_from_text(text)
        assert extracted == task_id1

    def test_no_uuid_found(self):
        """Test no UUID found in text."""
        text = "Please delete my scheduled task for tomorrow."

        extracted = extract_task_id_from_text(text)
        assert extracted is None

    def test_empty_text(self):
        """Test empty text input."""
        extracted = extract_task_id_from_text("")
        assert extracted is None

    def test_case_insensitive_uuid(self):
        """Test UUID extraction is case insensitive."""
        task_id = "abcdef01-1234-5678-9abc-123456789012"  # Use valid hex characters
        text = f"Delete task {task_id.upper()}"

        extracted = extract_task_id_from_text(text)
        assert extracted.lower() == task_id.lower()


class TestDeleteScheduledTasksTool:
    """Test the DeleteScheduledTasksTool functionality."""

    @requires_database
    def create_test_task(self, task_id: str, user_email: str, status: TaskStatus = TaskStatus.ACTIVE) -> Tasks:
        """Helper to create a real task in the test database."""
        db_connection = init_db_connection()
        with db_connection.get_session() as session:
            task = Tasks(
                task_id=task_id,
                status=status,
                email_request={"from": user_email, "subject": "Test Task"},
                scheduler_job_id=f"job_{task_id}",
                cron_expression="0 9 * * 1",
                email_id="test@example.com",
                created_at=datetime.now(timezone.utc)
            )
            session.add(task)
            session.commit()
            session.refresh(task)
            return task

    @requires_database
    @patch("mxtoai.tools.delete_scheduled_tasks_tool.remove_scheduled_job")
    def test_successful_task_deletion(self, mock_remove_job):
        """Test successful task deletion."""
        task_id = str(uuid.uuid4())
        user_email = "user@example.com"

        # Create a real task in the database
        self.create_test_task(task_id, user_email)
        mock_remove_job.return_value = True

        email_request = EmailRequest(from_email=user_email, to="dummy@to.com")
        tool = DeleteScheduledTasksTool(email_request=email_request)
        result = tool.forward(task_id=task_id)

        assert result["success"] is True
        assert result["task_id"] == task_id
        assert result["scheduler_removed"] is True

    @requires_database
    def test_task_not_found(self):
        """Test deletion when task is not found."""
        task_id = str(uuid.uuid4())
        user_email = "user@example.com"

        email_request = EmailRequest(from_email=user_email, to="dummy@to.com")
        tool = DeleteScheduledTasksTool(email_request=email_request)
        result = tool.forward(task_id=task_id)

        assert result["success"] is False
        assert result["error"] == "Task not found"
        assert result["task_id"] == task_id

    @requires_database
    def test_permission_denied_different_user(self):
        """Test deletion fails when user doesn't own the task."""
        task_id = str(uuid.uuid4())
        task_owner = "owner@example.com"
        requesting_user = "other@example.com"

        # Create a task owned by a different user
        self.create_test_task(task_id, task_owner)

        email_request = EmailRequest(from_email=requesting_user, to="dummy@to.com")
        tool = DeleteScheduledTasksTool(email_request=email_request)
        result = tool.forward(task_id=task_id)

        assert result["success"] is False
        assert result["error"] == "Permission denied"
        assert "own tasks" in result["message"]

    @requires_database
    @patch("mxtoai.tools.delete_scheduled_tasks_tool.remove_scheduled_job")
    def test_scheduler_removal_failure_continues_deletion(self, mock_remove_job):
        """Test that database deletion continues even if scheduler removal fails."""
        task_id = str(uuid.uuid4())
        user_email = "user@example.com"

        # Create a real task in the database
        self.create_test_task(task_id, user_email)

        # Setup mock scheduler removal to raise exception
        mock_remove_job.side_effect = Exception("Scheduler error")

        # Create tool and execute
        email_request = EmailRequest(from_email=user_email, to="dummy@to.com")
        tool = DeleteScheduledTasksTool(email_request=email_request)
        result = tool.forward(task_id=task_id)

        # Verify result - should still succeed
        assert result["success"] is True
        assert result["scheduler_removed"] is False
        assert result["database_updated"] is True

    def test_invalid_task_id_format(self):
        """Test tool handles invalid task ID format."""
        email_request = EmailRequest(from_email="user@example.com", to="dummy@to.com")
        tool = DeleteScheduledTasksTool(email_request=email_request)
        result = tool.forward(task_id="not-a-uuid")
        assert result["success"] is False
        assert "Invalid task ID format" in result["error"]

    @requires_database
    def test_find_user_tasks_with_results(self):
        """Test finding user tasks with results."""
        user_email = "test@example.com"
        task_id = str(uuid.uuid4())

        # Create a real task
        self.create_test_task(task_id, user_email)

        # Test find_user_tasks function directly
        db_connection = init_db_connection()
        with db_connection.get_session() as session:
            result = find_user_tasks(session, user_email)
            assert len(result) == 1
            assert result[0]["task_id"] == task_id
