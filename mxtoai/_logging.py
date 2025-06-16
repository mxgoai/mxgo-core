import logging
import os
import sys
from collections.abc import Sequence
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

import logfire
from dotenv import load_dotenv
from loguru import logger
from rich.console import Console

__all__ = ["get_logger", "get_smolagents_console", "span"]

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


class InterceptHandler(logging.Handler):
    """
    Intercept standard library logging and redirect to loguru.
    This captures logs from third-party libraries like LiteLLM, httpx, etc.
    """

    def emit(self, record):
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where originated the logged message
        frame, depth = logging.currentframe(), 2
        while frame and (frame.f_code.co_filename in (logging.__file__, __file__)):
            frame = frame.f_back
            depth += 1

        # Use the logger name from the original record for better identification
        logger_name = record.name if record.name else "unknown"

        # Get the formatted message
        try:
            message = record.getMessage()
        except Exception:
            message = str(record.msg)

        # Log through loguru with proper context
        logger.opt(depth=depth, exception=record.exc_info).bind(name=logger_name).log(level, message)


# Intercept standard library logging and redirect to loguru
def setup_stdlib_logging_intercept():
    """Set up interception of standard library logging."""
    # Create our intercept handler
    intercept_handler = InterceptHandler()

    # Configure root logger
    logging.root.handlers = [intercept_handler]
    logging.root.setLevel(LOG_LEVEL)

    # Configure loggers that should use the configured LOG_LEVEL
    verbose_loggers = [
        "smolagents",  # Capture smolagents verbose output
        "dramatiq",
    ]

    # Configure loggers that should only show ERROR level messages
    error_only_loggers = [
        "litellm",
        "httpx",
        "pika",  # RabbitMQ client
        "azure",
        "openai",
        "transformers",  # HuggingFace transformers
        "torch",  # PyTorch logging
        "requests",  # HTTP requests logging
        "urllib3",  # HTTP library used by requests
        "aiohttp",  # Async HTTP client
        "fontTools",  # Font manipulation library used in PDF generation
    ]

    # Set up verbose loggers with configured LOG_LEVEL
    for logger_name in verbose_loggers:
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.handlers = [intercept_handler]
        third_party_logger.setLevel(LOG_LEVEL)
        third_party_logger.propagate = True

    # Set up error-only loggers with ERROR level
    for logger_name in error_only_loggers:
        third_party_logger = logging.getLogger(logger_name)
        third_party_logger.handlers = [intercept_handler]
        third_party_logger.setLevel("ERROR")
        third_party_logger.propagate = True


# Set up the interception
setup_stdlib_logging_intercept()

# Log a test message to verify logging is working
logger.info("Logging initialized with level: {}", LOG_LEVEL)
logger.debug("Debug logging is enabled")


class LoguruRichConsole:
    """
    Custom Rich console that integrates with loguru.
    Captures smolagents Rich console output and feeds it into the loguru logging pipeline,
    which then goes to app.log, debug.log, and logfire for unified observability.
    """

    def __init__(self):
        """Initialize the loguru-integrated Rich console."""
        # Create a standard Rich console for terminal output
        self.terminal_console = Console()
        # Get loguru logger for capturing Rich output
        self.rich_logger = logger.bind(source="smolagents_rich")

    def print(self, *args, **kwargs):
        """Print to terminal and capture in loguru logging pipeline."""
        try:
            # Print to terminal as normal
            self.terminal_console.print(*args, **kwargs)

            # Capture the content for loguru logging
            # Convert Rich renderables to plain text for logging
            content_parts = []
            for arg in args:
                if hasattr(arg, "__rich__") or hasattr(arg, "__rich_console__"):
                    # For Rich renderables, capture their string representation
                    content_parts.append(str(arg))
                else:
                    content_parts.append(str(arg))

            content = " ".join(content_parts)

            # Determine log level based on style or content
            log_level = "INFO"  # Default level
            style = kwargs.get("style", "")
            if "error" in style.lower() or "red" in style.lower():
                log_level = "ERROR"
            elif "warning" in style.lower() or "yellow" in style.lower():
                log_level = "WARNING"
            elif "debug" in content.lower():
                log_level = "DEBUG"

            # Log to loguru (which feeds to app.log, debug.log, and logfire)
            self.rich_logger.log(log_level, "Rich Console: {}", content)

        except Exception as e:
            # Fallback logging if Rich integration fails
            error_msg = f"Rich console integration error: {e}"
            logger.error(error_msg)
            # Still try to print to terminal
            with suppress(Exception):
                self.terminal_console.print(*args, **kwargs)


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


def get_smolagents_console() -> LoguruRichConsole:
    """
    Get a Rich console for smolagents that integrates with loguru.
    This captures Rich console output and feeds it into the unified logging pipeline.
    """
    return LoguruRichConsole()
