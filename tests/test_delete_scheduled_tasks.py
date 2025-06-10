"""
Tests for the delete scheduled tasks tool and functionality.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from mxtoai.models import TaskStatus
from mxtoai.tools.delete_scheduled_tasks_tool import (
    DeleteScheduledTasksTool,
    DeleteTaskInput,
    extract_task_id_from_text,
    find_user_tasks,
)


class TestDeleteTaskInput:
    """Test the input validation for delete task requests."""

    def test_valid_input(self):
        """Test valid task deletion input."""
        task_id = str(uuid.uuid4())
        user_email = "user@example.com"

        input_data = DeleteTaskInput(
            task_id=task_id,
            user_email=user_email,
        )

        assert str(input_data.task_id) == task_id
        assert input_data.user_email == user_email

    def test_invalid_task_id_format(self):
        """Test validation fails for invalid UUID format."""
        with pytest.raises(ValidationError) as exc_info:
            DeleteTaskInput(
                task_id="not-a-uuid",
                user_email="user@example.com",
            )

        assert "Invalid task ID format" in str(exc_info.value)

    def test_missing_user_email(self):
        """Test validation fails for missing user email."""
        task_id = str(uuid.uuid4())

        with pytest.raises(ValidationError) as exc_info:
            DeleteTaskInput(
                task_id=task_id,
                user_email="",
            )

        assert "String should have at least 1 character" in str(exc_info.value)


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

    def create_mock_task(self, task_id: str, user_email: str, status: TaskStatus = TaskStatus.ACTIVE):
        """Helper to create mock task object."""
        mock_task = Mock()
        mock_task.task_id = task_id
        mock_task.status = status
        mock_task.email_request = {"from": user_email, "subject": "Test Task"}
        mock_task.scheduler_job_id = f"job_{task_id}"
        mock_task.cron_expression = "0 9 * * 1"
        mock_task.email_id = "test@example.com"
        mock_task.created_at = datetime.now(timezone.utc)
        return mock_task

    @patch("mxtoai.tools.delete_scheduled_tasks_tool.remove_scheduled_job")
    @patch("mxtoai.tools.delete_scheduled_tasks_tool.db_connection")
    def test_successful_task_deletion(self, mock_db_connection, mock_remove_job):
        """Test successful task deletion."""
        task_id = str(uuid.uuid4())
        user_email = "user@example.com"

        # Setup mock task
        mock_task = self.create_mock_task(task_id, user_email)

        # Setup mock database session
        mock_session = Mock()
        mock_session.exec.return_value.first.return_value = mock_task
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session

        # Setup mock scheduler removal
        mock_remove_job.return_value = True

        # Create tool and execute
        tool = DeleteScheduledTasksTool()
        result = tool.forward(task_id=task_id, user_email=user_email)

        # Verify result
        assert result["success"] is True
        assert result["task_id"] == task_id
        assert "Test Task" in result["task_description"]
        assert result["scheduler_removed"] is True

    @patch("mxtoai.tools.delete_scheduled_tasks_tool.db_connection")
    def test_task_not_found(self, mock_db_connection):
        """Test deletion when task is not found."""
        task_id = str(uuid.uuid4())
        user_email = "user@example.com"

        # Setup mock database session to return None
        mock_session = Mock()
        mock_session.exec.return_value.first.return_value = None
        mock_session.exec.return_value.all.return_value = []  # For find_user_tasks
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session

        # Create tool and execute
        tool = DeleteScheduledTasksTool()
        result = tool.forward(task_id=task_id, user_email=user_email)

        # Verify result
        assert result["success"] is False
        assert result["error"] == "Task not found"
        assert result["task_id"] == task_id

    @patch("mxtoai.tools.delete_scheduled_tasks_tool.db_connection")
    def test_permission_denied_different_user(self, mock_db_connection):
        """Test deletion fails when user doesn't own the task."""
        task_id = str(uuid.uuid4())
        task_owner = "owner@example.com"
        requesting_user = "other@example.com"

        # Setup mock task owned by different user
        mock_task = self.create_mock_task(task_id, task_owner)

        # Setup mock database session
        mock_session = Mock()
        mock_session.exec.return_value.first.return_value = mock_task
        mock_session.exec.return_value.all.return_value = []  # For find_user_tasks
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session

        # Create tool and execute
        tool = DeleteScheduledTasksTool()
        result = tool.forward(task_id=task_id, user_email=requesting_user)

        # Verify result
        assert result["success"] is False
        assert result["error"] == "Permission denied"
        assert "own tasks" in result["message"]

    @patch("mxtoai.tools.delete_scheduled_tasks_tool.remove_scheduled_job")
    @patch("mxtoai.tools.delete_scheduled_tasks_tool.db_connection")
    def test_scheduler_removal_failure_continues_deletion(self, mock_db_connection, mock_remove_job):
        """Test that database deletion continues even if scheduler removal fails."""
        task_id = str(uuid.uuid4())
        user_email = "user@example.com"

        # Setup mock task
        mock_task = self.create_mock_task(task_id, user_email)

        # Setup mock database session
        mock_session = Mock()
        mock_session.exec.return_value.first.return_value = mock_task
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session

        # Setup mock scheduler removal to raise exception
        mock_remove_job.side_effect = Exception("Scheduler error")

        # Create tool and execute
        tool = DeleteScheduledTasksTool()
        result = tool.forward(task_id=task_id, user_email=user_email)

        # Verify result - should still succeed
        assert result["success"] is True
        assert result["scheduler_removed"] is False
        assert result["database_updated"] is True

    @patch("mxtoai.tools.delete_scheduled_tasks_tool.db_connection")
    def test_corrupted_task_data(self, mock_db_connection):
        """Test handling of corrupted task email_request data."""
        task_id = str(uuid.uuid4())
        user_email = "user@example.com"

        # Setup mock task with corrupted email_request
        mock_task = Mock()
        mock_task.task_id = task_id
        mock_task.status = TaskStatus.ACTIVE
        mock_task.email_request = None  # This will cause corrupted data error

        # Setup mock database session
        mock_session = Mock()
        mock_session.exec.return_value.first.return_value = mock_task
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session

        # Create tool and execute
        tool = DeleteScheduledTasksTool()
        result = tool.forward(task_id=task_id, user_email=user_email)

        # Verify result
        assert result["success"] is False
        assert result["error"] == "Corrupted task data"

    def test_invalid_task_id_format(self):
        """Test tool handles invalid task ID format."""
        tool = DeleteScheduledTasksTool()
        result = tool.forward(task_id="invalid-uuid", user_email="user@example.com")

        # Should fail validation
        assert result["success"] is False
        assert "Invalid task ID format" in result["error"]

    @patch("mxtoai.tools.delete_scheduled_tasks_tool.db_connection")
    def test_database_exception_handling(self, mock_db_connection):
        """Test proper handling of database exceptions."""
        task_id = str(uuid.uuid4())
        user_email = "user@example.com"

        # Setup mock database session to raise exception
        mock_db_connection.get_session.side_effect = Exception("Database connection failed")

        # Create tool and execute
        tool = DeleteScheduledTasksTool()
        result = tool.forward(task_id=task_id, user_email=user_email)

        # Verify result
        assert result["success"] is False
        assert "Database connection failed" in result["error"]

    def test_extract_task_description(self):
        """Test task description extraction from email request."""
        tool = DeleteScheduledTasksTool()

        # Test with subject
        email_request = {
            "subject": "Weekly Sales Report",
            "textContent": "Please remind me to review the sales report"
        }
        description = tool._extract_task_description(email_request)
        assert description == "Subject: Weekly Sales Report"

        # Test with content only (longer than 100 characters to test truncation)
        email_request = {
            "textContent": "This is a long content that should be truncated after 100 characters to ensure proper display and testing of the truncation functionality"
        }
        description = tool._extract_task_description(email_request)
        assert description.startswith("Content: This is a long content")
        assert description.endswith("...")

        # Test with neither
        email_request = {}
        description = tool._extract_task_description(email_request)
        assert description == "Unknown task"

    @patch("mxtoai.tools.delete_scheduled_tasks_tool.db_connection")
    def test_find_user_tasks_with_results(self, mock_db_connection):
        """Test finding user tasks with results."""
        # Mock session and tasks
        mock_session = Mock()
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session

        # Create mock tasks
        task1 = Mock()
        task1.task_id = "12345678-1234-1234-1234-123456789012"
        task1.cron_expression = "0 9 * * 1"
        task1.email_id = "test@example.com"
        task1.status = TaskStatus.ACTIVE
        task1.created_at = datetime.now(timezone.utc)

        mock_session.exec.return_value.all.return_value = [task1]

        # Test the function
        result = find_user_tasks("test@example.com", mock_session)

        assert len(result) == 1
        assert result[0]["task_id"] == "12345678-1234-1234-1234-123456789012"
        assert result[0]["status"] == "ACTIVE"
