from datetime import datetime, timedelta, timezone

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
        # Weekly pattern (specific weekday)
        elif day == "*" and month == "*" and weekday not in {"*", "?"}:
            # If multiple days are specified (e.g., "1-5" or "1,3,5"), the minimum interval is 1 day.
            # Otherwise, it's a single day of the week, so the interval is 7 days.
            interval = timedelta(days=1) if "," in weekday or "-" in weekday else timedelta(weeks=1)

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
    """Converts schedule options from the newsletter request into a list of cron expressions."""
    if schedule.type == ScheduleType.IMMEDIATE:
        # Schedule for 1 minute in the future to be executed ASAP
        now = datetime.now(timezone.utc) + timedelta(minutes=1)
        return [f"{now.minute} {now.hour} {now.day} {now.month} *"]

    if schedule.type == ScheduleType.SPECIFIC_DATES:
        cron_list = []
        if not schedule.specific_dates:
            msg = "specific_dates must be provided for SPECIFIC_DATES schedule type."
            raise ValueError(msg)
        for dt_str in schedule.specific_dates:
            dt = datetime.fromisoformat(dt_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)  # Assume UTC if naive
            cron_list.append(f"{dt.minute} {dt.hour} {dt.day} {dt.month} *")
        return cron_list

    if schedule.type == ScheduleType.RECURRING_WEEKLY:
        if not schedule.recurring_weekly or not schedule.recurring_weekly.days:
            msg = "recurring_weekly with at least one day must be provided for RECURRING_WEEKLY schedule type."
            raise ValueError(msg)

        day_map = {"monday": 1, "tuesday": 2, "wednesday": 3, "thursday": 4, "friday": 5, "saturday": 6, "sunday": 0}
        days_of_week = ",".join(str(day_map[day]) for day in schedule.recurring_weekly.days)
        hour, minute = schedule.recurring_weekly.time.split(":")

        return [f"{minute} {hour} * * {days_of_week}"]

    msg = f"Unsupported schedule type: {schedule.type}"
    raise ValueError(msg)
