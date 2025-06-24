from pathlib import Path

# List of email addresses for which we skip sending email replies
# Useful for testing and development environments
SKIP_EMAIL_DELIVERY = [
    "test@example.com",
]
# Ensure attachments directory exists with absolute path
parent_dir = Path(__file__).parent.parent
ATTACHMENTS_DIR = (parent_dir / "attachments").resolve()
ATTACHMENTS_DIR.mkdir(exist_ok=True)

# Attachment limits (in megabytes)
MAX_ATTACHMENT_SIZE_MB = 15
MAX_TOTAL_ATTACHMENTS_SIZE_MB = 50
MAX_ATTACHMENTS_COUNT = 5

# Scheduled tasks configuration
SCHEDULED_TASKS_MINIMUM_INTERVAL_HOURS = 1
SCHEDULED_TASKS_MAX_PER_EMAIL = 5
