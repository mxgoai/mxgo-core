import os
import sys
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import logfire
from dotenv import load_dotenv
from loguru import logger

__all__ = ["get_logger", "span"]

# Load environment variables
load_dotenv()

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
LOGS_DIR = PROJECT_ROOT / "logs"

# Create logs directory if it doesn't exist
os.makedirs(LOGS_DIR, exist_ok=True)

# Get log level from environment or use default
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").strip()

# Define log format that works with and without 'source' in extra
LOG_FORMAT = (
    "<green>{process}:{level}: {time:YYYY-MM-DD at HH:mm:ss}</green> <blue>({name}::{function})</blue> {message}"
)

# Remove default handlers
logger.remove()

# Log to local filesystem as well,
# Keeping it here in case we want to use it sometimes it's more convenient to
# look for things using grep
logger.add(
    sys.stdout,
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    colorize=True,
)

# Add file handlers
logger.add(
    str(LOGS_DIR / "debug.log"),
    format=LOG_FORMAT,
    level="DEBUG",
    rotation="1 day",
    retention="1 year",
    compression="zip",
    enqueue=True,  # Use a queue for thread-safe logging
)

logger.add(
    str(LOGS_DIR / "app.log"),
    format=LOG_FORMAT,
    level=LOG_LEVEL,
    rotation="1 day",
    retention="1 year",
    compression="zip",
    enqueue=True,  # Use a queue for thread-safe logging
)

# Add logfire handler if token is available
if os.environ.get("LOGFIRE_TOKEN"):
    logfire_handler = logfire.loguru_handler()
    logger.add(**logfire_handler)
    logfire.configure(console=False)

# Log a test message to verify logging is working
logger.info("Logging initialized with level: {}", LOG_LEVEL)
logger.debug("Debug logging is enabled")


def get_logger(source: str) -> Any:
    """Get a logger instance bound with the source name."""
    return logger.bind(source=source)


@contextmanager
def span(
    msg_template: str, name: str | None = None, tags: Sequence[str] | None = None, **msg_template_kwargs: Any
) -> Any:
    """
    Context manager for creating spans in logging.

    Args:
        msg_template (str): The message template for the span.
        name (str | None): Optional name for the span.
        tags (Sequence[str] | None): Optional tags for the span.
        **msg_template_kwargs: Additional keyword arguments for the message template.

    Yields:
        Any: The span context manager or a dummy context manager.
    """
    # Check if LOGFIRE_TOKEN environment variable is defined
    if os.getenv("LOGFIRE_TOKEN"):
        if tags:
            # logs don't display on logfire dashboard if the type is not `str`
            tags = [str(tag) for tag in tags]
        # Use logfire.span if the environment variable is set
        with logfire.span(msg_template, _span_name=name, _tags=tags, **msg_template_kwargs) as _span:
            yield _span
    else:
        # Return a dummy context manager that does nothing
        yield
