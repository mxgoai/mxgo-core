"""
Tests for the scheduled task executor functionality.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, Mock, patch

import pytest

from mxtoai.models import TaskRunStatus, TaskStatus
from mxtoai.scheduled_task_executor import (
    _is_recurring_cron_expression,
    execute_scheduled_task,
    get_task_execution_status,
)


class TestScheduledTaskExecutor:
    """Test the scheduled task executor functionality."""

    def create_mock_task(self, task_id: str, status: TaskStatus = TaskStatus.ACTIVE,
                        start_time=None, expiry_time=None, cron_expression="0 9 * * 1"):
        """Helper to create mock task object."""
        mock_task = Mock()
        mock_task.task_id = task_id
        mock_task.status = status
        mock_task.email_request = {"from": "test@example.com", "subject": "Test Task"}
        mock_task.scheduler_job_id = f"job_{task_id}"
        mock_task.cron_expression = cron_expression
        mock_task.email_id = "test@example.com"
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.start_time = start_time
        mock_task.expiry_time = expiry_time
        return mock_task

    @patch("mxtoai.scheduled_task_executor._make_process_email_request")
    @patch("mxtoai.scheduled_task_executor.init_db_connection")
    def test_task_execution_before_start_time(self, mock_init_db, mock_make_request):
        """Test that task execution is skipped when current time is before start_time."""
        task_id = str(uuid.uuid4())
        future_start_time = datetime.now(timezone.utc) + timedelta(hours=1)

        mock_task = self.create_mock_task(task_id, start_time=future_start_time)

        # Setup database mocks
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_task
        mock_db_connection = MagicMock()
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
        mock_init_db.return_value = mock_db_connection

        # Execute the task
        execute_scheduled_task(task_id)

        # Verify that the HTTP request was not made (task was skipped)
        mock_make_request.assert_not_called()

    @patch("mxtoai.scheduled_task_executor._make_process_email_request")
    @patch("mxtoai.scheduled_task_executor.init_db_connection")
    def test_task_execution_after_expiry_time(self, mock_init_db, mock_make_request):
        """Test that task is marked as finished when current time is after expiry_time."""
        task_id = str(uuid.uuid4())
        past_expiry_time = datetime.now(timezone.utc) - timedelta(hours=1)

        mock_task = self.create_mock_task(task_id, expiry_time=past_expiry_time)

        # Setup database mocks
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_task
        mock_db_connection = MagicMock()
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
        mock_init_db.return_value = mock_db_connection

        # Execute the task
        execute_scheduled_task(task_id)

        # Verify that the task status was updated to FINISHED
        assert mock_task.status == TaskStatus.FINISHED
        mock_session.add.assert_called_with(mock_task)
        mock_session.commit.assert_called()

        # Verify that the HTTP request was not made (task was expired)
        mock_make_request.assert_not_called()

    @patch("mxtoai.scheduled_task_executor._make_process_email_request")
    @patch("mxtoai.scheduled_task_executor.init_db_connection")
    def test_task_execution_within_time_bounds(self, mock_init_db, mock_make_request):
        """Test that task executes normally when within start_time and expiry_time bounds."""
        task_id = str(uuid.uuid4())
        past_start_time = datetime.now(timezone.utc) - timedelta(hours=1)
        future_expiry_time = datetime.now(timezone.utc) + timedelta(hours=1)

        mock_task = self.create_mock_task(task_id, start_time=past_start_time, expiry_time=future_expiry_time)

        # Setup database mocks
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_task
        mock_db_connection = MagicMock()
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
        mock_init_db.return_value = mock_db_connection

        # Mock successful HTTP request
        mock_make_request.return_value = True

        # Execute the task
        execute_scheduled_task(task_id)

        # Verify that the HTTP request was made
        mock_make_request.assert_called_once()

        # Verify task status was updated to EXECUTING and then back to ACTIVE
        assert mock_session.add.call_count >= 2  # At least 2 calls for status updates

    @patch("mxtoai.scheduled_task_executor.init_db_connection")
    def test_get_task_execution_status_includes_time_fields(self, mock_init_db):
        """Test that get_task_execution_status includes start_time and expiry_time."""
        task_id = str(uuid.uuid4())
        start_time = datetime.now(timezone.utc)
        expiry_time = datetime.now(timezone.utc) + timedelta(days=1)

        mock_task = self.create_mock_task(task_id, start_time=start_time, expiry_time=expiry_time)

        # Setup database mocks
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_task
        mock_db_connection = MagicMock()
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
        mock_init_db.return_value = mock_db_connection

        # Get task status
        result = get_task_execution_status(task_id)

        # Verify that start_time and expiry_time are included
        assert result is not None
        assert "start_time" in result
        assert "expiry_time" in result
        assert result["start_time"] == start_time
        assert result["expiry_time"] == expiry_time

    def test_is_recurring_cron_expression_patterns(self):
        """Test the _is_recurring_cron_expression function with various patterns."""
        # Test recurring patterns
        assert _is_recurring_cron_expression("0 9 * * *") is True  # Daily
        assert _is_recurring_cron_expression("0 9 * * 1") is True  # Weekly
        assert _is_recurring_cron_expression("0 * * * *") is True  # Hourly
        assert _is_recurring_cron_expression("*/5 * * * *") is True  # Every 5 minutes

        # Test specific date patterns (still considered recurring for safety)
        assert _is_recurring_cron_expression("0 9 15 6 *") is True  # June 15th

        # Test invalid patterns
        assert _is_recurring_cron_expression("invalid") is False
        assert _is_recurring_cron_expression("0 9 * *") is False  # Wrong number of parts

    @patch("mxtoai.scheduled_task_executor.init_db_connection")
    def test_task_not_found(self, mock_init_db):
        """Test handling when task is not found in database."""
        task_id = str(uuid.uuid4())

        # Setup database mocks to return None (task not found)
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = None
        mock_db_connection = MagicMock()
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
        mock_init_db.return_value = mock_db_connection

        # Execute the task and expect it to raise an exception
        with pytest.raises(ValueError, match=f"Task {task_id} not found"):
            execute_scheduled_task(task_id)

    @patch("mxtoai.scheduled_task_executor._make_process_email_request")
    @patch("mxtoai.scheduled_task_executor.init_db_connection")
    def test_deleted_task_skipped(self, mock_init_db, mock_make_request):
        """Test that deleted tasks are skipped."""
        task_id = str(uuid.uuid4())
        mock_task = self.create_mock_task(task_id, status=TaskStatus.DELETED)

        # Setup database mocks
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = mock_task
        mock_db_connection = MagicMock()
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
        mock_init_db.return_value = mock_db_connection

        # Execute the task
        execute_scheduled_task(task_id)

        # Verify that the HTTP request was not made (task was deleted)
        mock_make_request.assert_not_called()


class TestTaskExecutionEdgeCases:
    """Test edge cases in task execution."""

    @patch("mxtoai.scheduled_task_executor.init_db_connection")
    def test_get_task_execution_status_not_found(self, mock_init_db):
        """Test get_task_execution_status when task is not found."""
        task_id = str(uuid.uuid4())

        # Setup database mocks to return None
        mock_session = MagicMock()
        mock_session.exec.return_value.first.return_value = None
        mock_db_connection = MagicMock()
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
        mock_init_db.return_value = mock_db_connection

        # Get task status
        result = get_task_execution_status(task_id)

        # Should return None when task not found
        assert result is None

    @patch("mxtoai.scheduled_task_executor.init_db_connection")
    def test_get_task_execution_status_with_task_run(self, mock_init_db):
        """Test get_task_execution_status includes latest task run information."""
        task_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        # Create mock task
        mock_task = Mock()
        mock_task.task_id = task_id
        mock_task.status = TaskStatus.ACTIVE
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)
        mock_task.cron_expression = "0 9 * * 1"
        mock_task.scheduler_job_id = f"job_{task_id}"
        mock_task.start_time = None
        mock_task.expiry_time = None

        # Create mock task run
        mock_task_run = Mock()
        mock_task_run.run_id = run_id
        mock_task_run.status = TaskRunStatus.COMPLETED
        mock_task_run.created_at = datetime.now(timezone.utc)
        mock_task_run.updated_at = datetime.now(timezone.utc)

        # Setup database mocks
        mock_session = MagicMock()
        # First call returns task, second call returns task run
        mock_session.exec.return_value.first.side_effect = [mock_task, mock_task_run]
        mock_db_connection = MagicMock()
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
        mock_init_db.return_value = mock_db_connection

        # Get task status
        result = get_task_execution_status(task_id)

        # Verify result includes task run information
        assert result is not None
        assert "latest_run" in result
        assert result["latest_run"]["run_id"] == run_id
        assert result["latest_run"]["status"] == TaskRunStatus.COMPLETED
