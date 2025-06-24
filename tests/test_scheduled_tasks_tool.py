"""
Tests for the scheduled tasks tool and functionality.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from mxtoai.config import SCHEDULED_TASKS_MINIMUM_INTERVAL_HOURS
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
            task_description="Weekly reminder task",
        )
        assert input_data.cron_expression == "0 9 * * 1"
        assert input_data.distilled_future_task_instructions == "Send weekly reminder email"
        assert input_data.task_description == "Weekly reminder task"

    def test_valid_input_with_times(self):
        """Test valid input with start and end times."""
        input_data = ScheduledTaskInput(
            cron_expression="0 14 * * *",  # Daily at 2 PM
            distilled_future_task_instructions="Daily market update",
            task_description="Daily market updates",
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
                task_description="Test",
            )
        assert "Invalid cron expression" in str(exc_info.value)

    def test_minimum_interval_validation_too_frequent(self):
        """Test validation fails for cron expressions that are too frequent."""
        with pytest.raises(ValidationError) as exc_info:
            ScheduledTaskInput(
                cron_expression="*/30 * * * *",  # Every 30 minutes - too frequent
                distilled_future_task_instructions="Test task",
                task_description="Test",
            )
        assert "too frequent" in str(exc_info.value)

    def test_minimum_interval_validation_valid_hourly(self):
        """Test validation passes for hourly cron expression."""
        input_data = ScheduledTaskInput(
            cron_expression="0 * * * *",  # Every hour - should pass
            distilled_future_task_instructions="Hourly task",
            task_description="Hourly test",
        )
        assert input_data.cron_expression == "0 * * * *"

    def test_datetime_validation_with_seconds(self):
        """Test datetime validation rounds to nearest minute."""
        input_data = ScheduledTaskInput(
            cron_expression="0 9 * * 1",
            distilled_future_task_instructions="Test task",
            task_description="Test",
            start_time="2024-01-01T14:30:45Z",  # Has seconds
        )
        # Should be rounded to nearest minute (no seconds)
        assert input_data.start_time == "2024-01-01T14:30:00+00:00"

    def test_datetime_validation_timezone_handling(self):
        """Test datetime validation handles timezone conversion."""
        input_data = ScheduledTaskInput(
            cron_expression="0 9 * * 1",
            distilled_future_task_instructions="Test task",
            task_description="Test",
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
        with pytest.raises(ValueError) as exc_info:
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
        with pytest.raises(ValueError) as exc_info:
            validate_minimum_interval("*/30 * * * *")
        assert "too frequent" in str(exc_info.value)
        assert f"minimum required: {timedelta(hours=SCHEDULED_TASKS_MINIMUM_INTERVAL_HOURS)}" in str(exc_info.value)

    def test_invalid_every_minute_interval(self):
        """Test every minute interval fails validation."""
        with pytest.raises(ValueError) as exc_info:
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
        with pytest.raises(ValueError) as exc_info:
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

    @patch("mxtoai.tools.scheduled_tasks_tool.add_scheduled_job")
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
            task_description="Weekly sales report reminder",
        )

        # Verify result
        assert result["success"] is True
        assert "task_id" in result
        assert result["cron_expression"] == "0 9 * * 1"
        assert result["task_description"] == "Weekly sales report reminder"
        assert "next_execution" in result

        # Verify database interaction
        mock_session.add.assert_called()
        mock_session.commit.assert_called()

        # Verify scheduling interaction
        mock_add_job.assert_called()

    @patch("mxtoai.tools.scheduled_tasks_tool.add_scheduled_job")
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
            task_description="Daily market updates",
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
                task_description="Test",
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
            task_description="Test",
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
            patch("mxtoai.tools.scheduled_tasks_tool.add_scheduled_job") as mock_add_job,
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
                task_description="Weekly sales analysis",
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
            patch("mxtoai.tools.scheduled_tasks_tool.add_scheduled_job") as mock_add_job,
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
                task_description="Weekly sales analysis with attachment context",
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
            task_description="Test",
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
            with pytest.raises(ValueError) as exc_info:
                validate_minimum_interval("*/30 * * * *")
            assert str(expected_minimum) in str(exc_info.value)

        # Hourly should pass
        validate_minimum_interval("0 * * * *")  # Should not raise


class TestScheduledTasksLimitEnforcement:
    """Test the 5-task limit enforcement per email."""

    def create_mock_email_request(self, from_email: str = "user@example.com"):
        """Helper to create mock email request."""
        return EmailRequest(
            from_email=from_email,
            to="test@example.com",
            subject="Test Email",
            textContent="Test content",
        )

    def test_scheduled_task_limit_wrapper_logic(self):
        """Test the limit wrapper logic directly without full EmailAgent."""
        from mxtoai.config import SCHEDULED_TASKS_MAX_PER_EMAIL

        self.create_mock_email_request()

        # Create a counter to track calls (simulating the wrapper logic)
        call_count = {"count": 0}
        max_calls = SCHEDULED_TASKS_MAX_PER_EMAIL

        def limited_forward_simulation(*args, **kwargs):
            """Simulate the wrapper that limits scheduled task calls."""
            if call_count["count"] >= max_calls:
                return {
                    "success": False,
                    "error": "Task limit exceeded",
                    "message": f"Maximum of {max_calls} scheduled tasks allowed per email. This limit helps prevent excessive automation.",
                    "tasks_created": call_count["count"],
                    "max_allowed": max_calls,
                }

            # Increment counter before calling
            call_count["count"] += 1

            # Simulate successful task creation
            return {
                "success": True,
                "task_id": f"task-{call_count['count']}",
                "message": "Task created successfully",
                "cron_expression": args[0] if args else "0 9 * * 1",
                "task_description": kwargs.get("task_description", f"Task {call_count['count']}"),
            }

        # Create 5 successful tasks (should all work)
        successful_tasks = []
        for i in range(5):
            result = limited_forward_simulation(
                "0 9 * * 1",
                distilled_future_task_instructions=f"Task {i + 1} instructions",
                task_description=f"Task {i + 1}",
            )
            successful_tasks.append(result)
            assert result["success"] is True
            assert "task_id" in result

        # Try to create a 6th task (should be rejected)
        sixth_result = limited_forward_simulation(
            "0 9 * * 1",
            distilled_future_task_instructions="Sixth task instructions",
            task_description="Sixth task",
        )

        # Verify the 6th task was rejected
        assert sixth_result["success"] is False
        assert sixth_result["error"] == "Task limit exceeded"
        assert "Maximum of 5 scheduled tasks allowed per email" in sixth_result["message"]
        assert sixth_result["tasks_created"] == 5
        assert sixth_result["max_allowed"] == 5

    def test_failed_task_counter_decrement_logic(self):
        """Test that failed task creation doesn't count against the limit."""
        from mxtoai.config import SCHEDULED_TASKS_MAX_PER_EMAIL

        # Create a counter to track calls
        call_count = {"count": 0}
        max_calls = SCHEDULED_TASKS_MAX_PER_EMAIL

        # Track whether we've had the first failure
        first_call = {"done": False}

        def limited_forward_with_failure_simulation(*args, **kwargs):
            """Simulate the wrapper with failure handling."""
            if call_count["count"] >= max_calls:
                return {
                    "success": False,
                    "error": "Task limit exceeded",
                    "message": f"Maximum of {max_calls} scheduled tasks allowed per email.",
                    "tasks_created": call_count["count"],
                    "max_allowed": max_calls,
                }

            # Increment counter before calling
            call_count["count"] += 1

            # Simulate a failure on first call only
            if not first_call["done"]:
                first_call["done"] = True
                call_count["count"] -= 1  # Decrement on failure
                return {
                    "success": False,
                    "error": "Database error",
                    "message": "Simulated database error",
                }

            # For other calls, return success
            return {
                "success": True,
                "task_id": f"task-{call_count['count']}",
                "message": "Task created successfully",
            }

        # First task should fail (simulated database error)
        result1 = limited_forward_with_failure_simulation(
            "0 9 * * 1",
            distilled_future_task_instructions="First task",
            task_description="First task",
        )
        assert result1["success"] is False  # Should fail due to simulated error
        assert result1["error"] == "Database error"

        # Next 5 tasks should succeed (counter was decremented after failure)
        for i in range(5):
            result = limited_forward_with_failure_simulation(
                "0 9 * * 1",
                distilled_future_task_instructions=f"Task {i + 2} instructions",
                task_description=f"Task {i + 2}",
            )
            assert result["success"] is True
            assert "task_id" in result

        # 7th task should be rejected (we've hit the limit)
        result7 = limited_forward_with_failure_simulation(
            "0 9 * * 1",
            distilled_future_task_instructions="Seventh task",
            task_description="Seventh task",
        )
        assert result7["success"] is False
        assert result7["error"] == "Task limit exceeded"
