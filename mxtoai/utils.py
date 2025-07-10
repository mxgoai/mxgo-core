from datetime import datetime, timezone


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
