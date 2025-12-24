from datetime import datetime, timedelta, timezone

from croniter import croniter

from mxgo.schemas import ScheduleOptions, ScheduleType


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


def validate_datetime_field(value: str, field_name: str) -> str:
    """
    Validate and normalize a datetime field for scheduled tasks.

    Args:
        value: The datetime string to validate
        field_name: Name of the field being validated (for error messages)

    Returns:
        Normalized ISO format datetime string

    Raises:
        ValueError: If the datetime format is invalid

    """
    if value is None:
        return value
    try:
        # Parse the datetime string and ensure it has a timezone
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Round to the nearest minute
        dt = round_to_nearest_minute(dt)

        # Return the rounded datetime as an ISO string
        return dt.isoformat()
    except ValueError as e:
        msg = f"Invalid datetime format for {field_name}: {e}"
        raise ValueError(msg) from e


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
        # Weekly pattern with multiple days
        elif day == "*" and month == "*" and weekday not in {"*", "?"}:
            # This handles cases like "1,3,5" (Mon, Wed, Fri)
            if "," in weekday:
                days_of_week = sorted([int(d) for d in weekday.split(",")])
                if len(days_of_week) <= 1:
                    return timedelta(weeks=1)

                min_diff = 7
                # Calculate interval between consecutive days
                for i in range(1, len(days_of_week)):
                    diff = days_of_week[i] - days_of_week[i - 1]
                    min_diff = min(min_diff, diff)

                # Calculate wrap-around interval (e.g., from Friday to Monday)
                wrap_around_diff = (days_of_week[0] + 7) - days_of_week[-1]
                min_diff = min(min_diff, wrap_around_diff)

                return timedelta(days=min_diff)

            # Single day of the week
            return timedelta(weeks=1)

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


def convert_schedule_to_cron_list(schedule: ScheduleOptions) -> list[str]:
    """
    Converts schedule options from the newsletter request into a list of valid cron expressions.

    Raises:
        ValueError: If the schedule configuration is invalid or results in an invalid cron expression.

    """
    cron_expressions = []

    if schedule.type == ScheduleType.IMMEDIATE:
        # Schedule for 1 minute in the future to be executed as soon as possible.
        now = datetime.now(timezone.utc) + timedelta(minutes=1)
        cron_str = f"{now.minute} {now.hour} {now.day} {now.month} *"
        cron_expressions.append(cron_str)

    elif schedule.type == ScheduleType.SPECIFIC_DATES:
        if not schedule.specific_datetime:
            msg = "specific_datetime must be provided for SPECIFIC_DATES schedule type."
            raise ValueError(msg)

        dt = datetime.fromisoformat(schedule.specific_datetime)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)  # Assume UTC if timezone is not specified

        # Ensure the scheduled time is not in the past
        if dt <= datetime.now(timezone.utc):
            msg = "Specific datetime for a one-time schedule must be in the future."
            raise ValueError(msg)

        cron_str = f"{dt.minute} {dt.hour} {dt.day} {dt.month} *"
        cron_expressions.append(cron_str)

    elif schedule.type == ScheduleType.RECURRING_WEEKLY:
        if not schedule.weekly_schedule or not schedule.weekly_schedule.days:
            msg = "weekly_schedule with at least one day must be provided for RECURRING_WEEKLY type."
            raise ValueError(msg)

        # Days are now expected to be integers (0=Sunday, 1=Monday, ..., 6=Saturday)
        days_of_week = ",".join(map(str, sorted(schedule.weekly_schedule.days)))

        try:
            hour, minute = schedule.weekly_schedule.time.split(":")
            # Basic validation for time format
            if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):  # noqa: PLR2004
                msg = "Invalid time format."
                raise ValueError(msg)
        except ValueError as e:
            msg = f"Invalid time format in weekly_schedule: {schedule.weekly_schedule.time}"
            raise ValueError(msg) from e

        cron_str = f"{minute} {hour} * * {days_of_week}"
        cron_expressions.append(cron_str)

    else:
        msg = f"Unsupported schedule type: {schedule.type}"
        raise ValueError(msg)

    # Validate all generated cron expressions before returning
    for cron_expr in cron_expressions:
        if not croniter.is_valid(cron_expr):
            msg = f"Generated an invalid cron expression: '{cron_expr}'"
            raise ValueError(msg)

    return cron_expressions
