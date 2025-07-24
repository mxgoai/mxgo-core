import os
from pathlib import Path

from dotenv import load_dotenv

from mxgo.schemas import UserPlan

# Load environment variables
load_dotenv()

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
RATE_LIMITS_BY_PLAN = {
    UserPlan.BETA: {
        "hour": {"limit": 10, "period_seconds": 3600, "expiry_seconds": 3600 * 2},  # 2hr expiry for 1hr window
        "day": {"limit": 30, "period_seconds": 86400, "expiry_seconds": 86400 + 3600},  # 25hr expiry for 24hr window
        "month": {
            "limit": 200,
            "period_seconds": 30 * 86400,
            "expiry_seconds": (30 * 86400) + 86400,
        },  # 31day expiry for 30day window
    },
    UserPlan.PRO: {
        "hour": {"limit": 50, "period_seconds": 3600, "expiry_seconds": 3600 * 2},  # 2hr expiry for 1hr window
        "day": {"limit": 100, "period_seconds": 86400, "expiry_seconds": 86400 + 3600},  # 25hr expiry for 24hr window
        "month": {
            "limit": 1000,
            "period_seconds": 30 * 86400,
            "expiry_seconds": (30 * 86400) + 86400,
        },
    },
}
RATE_LIMIT_PER_DOMAIN_HOUR = {  # Consistent structure for domain limits
    "hour": {"limit": 50, "period_seconds": 3600, "expiry_seconds": 3600 * 2}
}
PERIOD_EXPIRY = {
    "hour": 3600 * 2,  # 2 hours
    "day": 86400 + 3600,  # 25 hours
    "month": 30 * 86400 + 86400,  # 31 days
}
DODO_API_KEY = os.getenv("DODO_API_KEY")
PRO_PLAN_PRODUCT_ID = os.getenv("PRO_PLAN_PRODUCT_ID")
DODO_API_BASE_URL = "https://live.dodopayments.com"
