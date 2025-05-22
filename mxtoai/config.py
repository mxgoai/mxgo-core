from pathlib import Path
from typing import ClassVar

# List of email addresses for which we skip sending email replies
# Useful for testing and development environments
SKIP_EMAIL_DELIVERY: ClassVar[list[str]] = [
    "test@example.com",
]
# Ensure attachments directory exists with absolute path
current_file_path = Path(__file__).resolve()
parent_dir = current_file_path.parent.parent
ATTACHMENTS_DIR = (parent_dir / "attachments").resolve()
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

# Attachment limits (in megabytes)
MAX_ATTACHMENT_SIZE_MB = 15
MAX_TOTAL_ATTACHMENTS_SIZE_MB = 50
MAX_ATTACHMENTS_COUNT = 5
