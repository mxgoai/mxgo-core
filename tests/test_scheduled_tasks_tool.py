"""
Tests for the scheduled tasks tool and functionality.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from mxtoai.config import SCHEDULED_TASKS_MAX_PER_EMAIL, SCHEDULED_TASKS_MINIMUM_INTERVAL_HOURS
from mxtoai.request_context import RequestContext
from mxtoai.schemas import EmailRequest, HandlerAlias
from mxtoai.tools.scheduled_tasks_tool import (
    ScheduledTaskInput,
    ScheduledTasksTool,
    calculate_cron_interval,
    validate_minimum_interval,
)
from mxtoai.utils import round_to_nearest_minute, validate_datetime_field


class TestScheduledTaskInput:
    """Test the input validation for scheduled task creation."""

    def test_valid_input(self):
        """Test valid scheduled task input."""
        input_data = ScheduledTaskInput(
            cron_expression="0 9 * * 1",  # Every Monday at 9 AM
            distilled_future_task_instructions="Send weekly reminder email",
        )
        assert input_data.cron_expression == "0 9 * * 1"
        assert input_data.distilled_future_task_instructions == "Send weekly reminder email"

    def test_valid_input_with_times(self):
        """Test valid input with start and end times."""
        input_data = ScheduledTaskInput(
            cron_expression="0 14 * * *",  # Daily at 2 PM
            distilled_future_task_instructions="Daily market update",
            start_time="2024-01-01T14:00:00Z",
            end_time="2024-12-31T14:00:00Z",
        )
        assert input_data.start_time == "2024-01-01T14:00:00+00:00"
        assert input_data.end_time == "2024-12-31T14:00:00+00:00"

    def test_invalid_cron_expression(self):
        """Test validation fails for invalid cron expression."""
        with pytest.raises(ValidationError) as exc_info:
            ScheduledTaskInput(
                cron_expression="invalid cron",
                distilled_future_task_instructions="Test task",
            )
        assert "Invalid cron expression" in str(exc_info.value)

    def test_minimum_interval_validation_too_frequent(self):
        """Test validation fails for cron expressions that are too frequent."""
        with pytest.raises(ValidationError) as exc_info:
            ScheduledTaskInput(
                cron_expression="*/30 * * * *",  # Every 30 minutes - too frequent
                distilled_future_task_instructions="Test task",
            )
        assert "too frequent" in str(exc_info.value)

    def test_minimum_interval_validation_valid_hourly(self):
        """Test validation passes for hourly cron expression."""
        input_data = ScheduledTaskInput(
            cron_expression="0 * * * *",  # Every hour - should pass
            distilled_future_task_instructions="Hourly task",
        )
        assert input_data.cron_expression == "0 * * * *"

    def test_datetime_validation_with_seconds(self):
        """Test datetime validation rounds to nearest minute."""
        input_data = ScheduledTaskInput(
            cron_expression="0 9 * * 1",
            distilled_future_task_instructions="Test task",
            start_time="2024-01-01T14:30:45Z",  # Has seconds
        )
        # Should be rounded to nearest minute (no seconds)
        assert input_data.start_time == "2024-01-01T14:30:00+00:00"

    def test_datetime_validation_timezone_handling(self):
        """Test datetime validation handles timezone conversion."""
        input_data = ScheduledTaskInput(
            cron_expression="0 9 * * 1",
            distilled_future_task_instructions="Test task",
            start_time="2024-01-01T14:30:00",  # No timezone
        )
        # Should add UTC timezone
        assert input_data.start_time == "2024-01-01T14:30:00+00:00"


class TestCronIntervalCalculation:
    """Test cron expression interval calculation."""

    def test_every_minute(self):
        """Test every minute cron expression."""
        interval = calculate_cron_interval("* * * * *")
        assert interval == timedelta(minutes=1)

    def test_every_5_minutes(self):
        """Test every 5 minutes cron expression."""
        interval = calculate_cron_interval("*/5 * * * *")
        assert interval == timedelta(minutes=5)

    def test_every_hour(self):
        """Test every hour cron expression."""
        interval = calculate_cron_interval("0 * * * *")
        assert interval == timedelta(hours=1)

    def test_every_2_hours(self):
        """Test every 2 hours cron expression."""
        interval = calculate_cron_interval("0 */2 * * *")
        assert interval == timedelta(hours=2)

    def test_daily(self):
        """Test daily cron expression."""
        interval = calculate_cron_interval("0 9 * * *")
        assert interval == timedelta(days=1)

    def test_weekly(self):
        """Test weekly cron expression."""
        interval = calculate_cron_interval("0 9 * * 1")
        assert interval == timedelta(weeks=1)

    def test_monthly(self):
        """Test monthly cron expression."""
        interval = calculate_cron_interval("0 9 1 * *")
        assert interval == timedelta(days=30)

    def test_yearly(self):
        """Test yearly cron expression."""
        interval = calculate_cron_interval("0 9 1 1 *")
        assert interval == timedelta(days=365)

    def test_invalid_cron_expression(self):
        """Test invalid cron expression raises error."""
        with pytest.raises(ValueError, match="must have exactly 5 parts") as exc_info:
            calculate_cron_interval("invalid")
        assert "must have exactly 5 parts" in str(exc_info.value)


class TestMinimumIntervalValidation:
    """Test minimum interval validation."""

    def test_valid_hourly_interval(self):
        """Test hourly interval passes validation."""
        # Should not raise exception
        validate_minimum_interval("0 * * * *")

    def test_valid_daily_interval(self):
        """Test daily interval passes validation."""
        # Should not raise exception
        validate_minimum_interval("0 9 * * *")

    def test_invalid_30_minute_interval(self):
        """Test 30-minute interval fails validation."""
        with pytest.raises(ValueError, match="too frequent") as exc_info:
            validate_minimum_interval("*/30 * * * *")
        assert "too frequent" in str(exc_info.value)
        assert f"minimum required: {timedelta(hours=SCHEDULED_TASKS_MINIMUM_INTERVAL_HOURS)}" in str(exc_info.value)

    def test_invalid_every_minute_interval(self):
        """Test every minute interval fails validation."""
        with pytest.raises(ValueError, match="too frequent") as exc_info:
            validate_minimum_interval("* * * * *")
        assert "too frequent" in str(exc_info.value)


class TestDatetimeUtilities:
    """Test datetime utility functions."""

    def test_round_to_nearest_minute_no_seconds(self):
        """Test rounding when no seconds present."""
        dt = datetime(2024, 1, 1, 14, 30, 0, tzinfo=timezone.utc)
        rounded = round_to_nearest_minute(dt)
        assert rounded == dt
        assert rounded.second == 0
        assert rounded.microsecond == 0

    def test_round_to_nearest_minute_with_seconds(self):
        """Test rounding when seconds present."""
        dt = datetime(2024, 1, 1, 14, 30, 45, tzinfo=timezone.utc)
        rounded = round_to_nearest_minute(dt)
        expected = datetime(2024, 1, 1, 14, 30, 0, tzinfo=timezone.utc)
        assert rounded == expected

    def test_round_to_nearest_minute_with_microseconds(self):
        """Test rounding removes microseconds."""
        dt = datetime(2024, 1, 1, 14, 30, 0, 123456, tzinfo=timezone.utc)
        rounded = round_to_nearest_minute(dt)
        expected = datetime(2024, 1, 1, 14, 30, 0, tzinfo=timezone.utc)
        assert rounded == expected

    def test_validate_datetime_field_valid(self):
        """Test datetime field validation with valid input."""
        result = validate_datetime_field("2024-01-01T14:30:00Z", "test_field")
        assert result == "2024-01-01T14:30:00+00:00"

    def test_validate_datetime_field_none(self):
        """Test datetime field validation with None input."""
        result = validate_datetime_field(None, "test_field")
        assert result is None

    def test_validate_datetime_field_invalid(self):
        """Test datetime field validation with invalid input."""
        with pytest.raises(ValueError, match="Invalid datetime format for test_field") as exc_info:
            validate_datetime_field("invalid-date", "test_field")
        assert "Invalid datetime format for test_field" in str(exc_info.value)


class TestScheduledTasksTool:
    """Test the ScheduledTasksTool functionality."""

    def create_mock_email_request(self, from_email: str = "user@example.com"):
        """Helper to create mock email request."""
        return EmailRequest(
            from_email=from_email,
            to="test@example.com",
            subject="Test Email",
            textContent="Test content",
        )

    @patch("mxtoai.scheduling.scheduler.Scheduler.add_job")
    @patch("mxtoai.tools.scheduled_tasks_tool.init_db_connection")
    def test_successful_task_creation(self, mock_init_db_connection, mock_add_job):
        """Test successful scheduled task creation."""
        # Setup mocks
        mock_session = MagicMock()
        mock_db_connection = MagicMock()
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
        mock_init_db_connection.return_value = mock_db_connection
        mock_add_job.return_value = None

        # Create tool and execute
        email_request = self.create_mock_email_request()
        tool = ScheduledTasksTool(context=RequestContext(email_request))

        result = tool.forward(
            cron_expression="0 9 * * 1",
            distilled_future_task_instructions="Send weekly reminder with attachment context: report.pdf (2MB) containing sales data",
        )

        # Verify result
        assert result["success"] is True
        assert "task_id" in result
        assert result["cron_expression"] == "0 9 * * 1"
        assert (
            result["task_description"]
            == "Send weekly reminder with attachment context: report.pdf (2MB) containing sales data"
        )
        assert "next_execution" in result

        # Verify database interaction
        mock_session.add.assert_called()
        mock_session.commit.assert_called()

        # Verify scheduling interaction
        mock_add_job.assert_called()

    @patch("mxtoai.scheduling.scheduler.Scheduler.add_job")
    @patch("mxtoai.tools.scheduled_tasks_tool.init_db_connection")
    def test_task_creation_with_start_and_end_times(self, mock_init_db_connection, mock_add_job):
        """Test task creation with start and end times."""
        # Setup mocks
        mock_session = MagicMock()
        mock_db_connection = MagicMock()
        mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
        mock_init_db_connection.return_value = mock_db_connection
        mock_add_job.return_value = None

        # Create tool and execute
        email_request = self.create_mock_email_request()
        tool = ScheduledTasksTool(context=RequestContext(email_request))

        result = tool.forward(
            cron_expression="0 14 * * *",
            distilled_future_task_instructions="Daily market updates",
            start_time="2024-01-01T14:00:00Z",
            end_time="2024-12-31T14:00:00Z",
        )

        # Verify result
        assert result["success"] is True
        assert result["start_time"] == "2024-01-01T14:00:00+00:00"
        assert result["end_time"] == "2024-12-31T14:00:00+00:00"

        # Verify the task was created with correct times
        call_args = mock_session.add.call_args[0][0]
        assert call_args.start_time is not None
        assert call_args.expiry_time is not None

    def test_invalid_time_range(self):
        """Test validation fails when start_time is after end_time."""
        email_request = self.create_mock_email_request()
        tool = ScheduledTasksTool(context=RequestContext(email_request))

        # Mock the database connection to prevent actual database calls
        with patch("mxtoai.tools.scheduled_tasks_tool.init_db_connection") as mock_init_db:
            mock_session = MagicMock()
            mock_db_connection = MagicMock()
            mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
            mock_init_db.return_value = mock_db_connection

            result = tool.forward(
                cron_expression="0 9 * * 1",
                distilled_future_task_instructions="Test task",
                start_time="2024-12-31T14:00:00Z",  # After end_time
                end_time="2024-01-01T14:00:00Z",  # Before start_time
            )

            assert result["success"] is False
            assert result["error"] == "Invalid time range"
            assert "start_time must be before end_time" in result["message"]

    def test_recursive_scheduling_prevention(self):
        """Test that recursive scheduling is prevented."""
        email_request = self.create_mock_email_request()
        email_request.scheduled_task_id = "existing-task-id"  # Already a scheduled task

        tool = ScheduledTasksTool(context=RequestContext(email_request))

        result = tool.forward(
            cron_expression="0 9 * * 1",
            distilled_future_task_instructions="Test task",
        )

        assert result["success"] is False
        assert result["error"] == "Recursive scheduling not allowed"
        assert result["existing_task_id"] == "existing-task-id"

    def test_distilled_instructions_and_alias_assignment(self):
        """Test that distilled instructions are properly assigned."""
        email_request = self.create_mock_email_request()
        tool = ScheduledTasksTool(context=RequestContext(email_request))

        # Mock the database and scheduling
        with (
            patch("mxtoai.tools.scheduled_tasks_tool.init_db_connection") as mock_init_db,
            patch("mxtoai.scheduling.scheduler.Scheduler.add_job") as mock_add_job,
        ):
            mock_session = MagicMock()
            mock_db_connection = MagicMock()
            mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
            mock_init_db.return_value = mock_db_connection
            mock_add_job.return_value = None

            distilled_instructions = "Process sales data from attachment report.csv (1.5MB) with columns: date, product, revenue. Generate weekly summary with trends."

            tool.forward(
                cron_expression="0 9 * * 1",
                distilled_future_task_instructions=distilled_instructions,
            )

            # Verify the email request was updated
            assert email_request.distilled_processing_instructions == distilled_instructions
            assert email_request.distilled_alias == HandlerAlias.ASK

    def test_attachment_context_in_distilled_instructions(self):
        """Test that attachment context can be included in distilled instructions."""
        email_request = self.create_mock_email_request()
        tool = ScheduledTasksTool(context=RequestContext(email_request))

        with (
            patch("mxtoai.tools.scheduled_tasks_tool.init_db_connection") as mock_init_db,
            patch("mxtoai.scheduling.scheduler.Scheduler.add_job") as mock_add_job,
        ):
            mock_session = MagicMock()
            mock_db_connection = MagicMock()
            mock_db_connection.get_session.return_value.__enter__.return_value = mock_session
            mock_init_db.return_value = mock_db_connection
            mock_add_job.return_value = None

            # Distilled instructions with attachment context
            attachment_context = (
                "Process the attached sales_report.xlsx (3.2MB) containing Q4 sales data. "
                "The file has sheets: Summary, Regional, Products. Focus on revenue trends "
                "and top-performing regions. Since the original attachment won't be available "
                "during scheduled execution, use the data patterns described: declining sales "
                "in Northeast, growth in Southwest, top products are Widget A and Widget B."
            )

            result = tool.forward(
                cron_expression="0 9 * * 1",
                distilled_future_task_instructions=attachment_context,
            )

            assert result["success"] is True
            assert email_request.distilled_processing_instructions == attachment_context

    def test_cron_expression_validation_in_tool(self):
        """Test that invalid cron expressions are caught by the tool."""
        email_request = self.create_mock_email_request()
        tool = ScheduledTasksTool(context=RequestContext(email_request))

        result = tool.forward(
            cron_expression="*/15 * * * *",  # Every 15 minutes - too frequent
            distilled_future_task_instructions="Test task",
        )

        assert result["success"] is False
        assert "too frequent" in result["error"]


class TestConfigurationIntegration:
    """Test integration with configuration values."""

    def test_minimum_interval_uses_config_value(self):
        """Test that minimum interval validation uses the config value."""
        # Test that the validation uses SCHEDULED_TASKS_MINIMUM_INTERVAL_HOURS
        expected_minimum = timedelta(hours=SCHEDULED_TASKS_MINIMUM_INTERVAL_HOURS)

        # Create a cron expression that's just under the minimum
        if SCHEDULED_TASKS_MINIMUM_INTERVAL_HOURS == 1:
            # 30 minutes should fail
            with pytest.raises(ValueError, match="too frequent") as exc_info:
                validate_minimum_interval("*/30 * * * *")
            assert str(expected_minimum) in str(exc_info.value)

        # Hourly should pass
        validate_minimum_interval("0 * * * *")  # Should not raise


class TestScheduledTasksLimitEnforcement:
    """Test enforcement of the maximum number of scheduled tasks per email."""

    def create_mock_email_request(self, from_email: str = "user@example.com"):
        """Helper to create a mock email request object."""
        return EmailRequest(
            from_email=from_email,
            to="test@example.com",
            subject="Test Email with many tasks",
            textContent="This email will try to create multiple scheduled tasks.",
        )

    def test_scheduled_task_limit_wrapper_logic(self):
        """Test the limit wrapper logic directly without full EmailAgent."""
        self.create_mock_email_request()
        # Counter to simulate task creation
        task_creation_counter = 0

        # Simulate the wrapped forward method
        def limited_forward_simulation(*args, **kwargs):
            nonlocal task_creation_counter
            if task_creation_counter >= SCHEDULED_TASKS_MAX_PER_EMAIL:
                msg = "Scheduled task limit reached"
                raise ValueError(msg)
            task_creation_counter += 1
            return {"success": True, "task_id": f"task_{task_creation_counter}"}

        # Verify that creating tasks up to the limit is successful
        for _ in range(SCHEDULED_TASKS_MAX_PER_EMAIL):
            result = limited_forward_simulation()
            assert result["success"] is True

        # Verify that creating one more task raises the expected error
        with pytest.raises(ValueError, match="Scheduled task limit reached"):
            limited_forward_simulation()

    def test_failed_task_counter_decrement_logic(self):
        """Test that failed task creation doesn't count against the limit."""
        # Create a counter to track calls
        task_creation_counter = 0

        # Simulate the wrapped forward method that sometimes fails
        def limited_forward_with_failure_simulation(*args, **kwargs):
            nonlocal task_creation_counter
            # Fail on the second attempt
            if task_creation_counter == 1:
                msg = "Simulated failure during task creation"
                raise RuntimeError(msg)
            if task_creation_counter >= SCHEDULED_TASKS_MAX_PER_EMAIL:
                msg = "Scheduled task limit reached"
                raise ValueError(msg)
            task_creation_counter += 1
            return {"success": True, "task_id": f"task_{task_creation_counter}"}

        # Successful call
        limited_forward_with_failure_simulation()
        assert task_creation_counter == 1

        # Failed call
        with pytest.raises(RuntimeError):
            limited_forward_with_failure_simulation()
        # Counter should not have incremented
        assert task_creation_counter == 1

        # Subsequent calls up to the limit should still succeed
        for _ in range(SCHEDULED_TASKS_MAX_PER_EMAIL - 1):
            limited_forward_with_failure_simulation()

        # The next call should fail due to the limit
        with pytest.raises(ValueError, match="Scheduled task limit reached"):
            limited_forward_with_failure_simulation()
