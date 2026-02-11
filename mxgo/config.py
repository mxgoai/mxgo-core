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

NEWSLETTER_LIMITS_BY_PLAN = {
    UserPlan.BETA: {
        "max_tasks": 6,
        "min_interval_days": 7,
    },
    UserPlan.PRO: {
        "max_tasks": 40,
        "min_interval_days": 1,
    },
}

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

# System capabilities - extracted from email handles and their templates
SYSTEM_CAPABILITIES = """## Available Email Processing Handles

- **summarize**: Systematically analyze and summarize content from all sources with clear structure and action focus. Processes email content, attachments, and external references to provide executive summaries, main points, action items, and additional context.

- **research**: Conduct comprehensive research and provide detailed analysis with proper sections and citations. Uses deep research tools to gather current information, analyze findings, and provide supporting evidence with academic tone.

- **simplify**: Transform complex content into clear, accessible explanations using simple language and relatable examples. Breaks down technical jargon, adds helpful analogies, and makes content understandable to general audiences.

- **ask**: Execute custom tasks and workflows systematically with research, analysis, and professional presentation. Handles any custom request, research needs, content creation, and provides comprehensive solutions with proper formatting.

- **fact-check**: Systematically verify claims and statements with comprehensive source validation and transparent uncertainty handling. Extracts all verifiable claims, searches for evidence, cross-references multiple sources, and provides clear verification status.

- **background-research**: Conduct comprehensive business intelligence research on individuals and organizations. Provides strategic insights for business decisions, company analysis, professional profiles, and competitive context.

- **translate**: Provide accurate translations with cultural context preservation and clear explanation of translation decisions. Detects source language, chooses appropriate translation approach, and provides cultural adaptations.

- **meeting**: Intelligently extract, research, and schedule meetings or appointments with proper validation. Handles participant research, time resolution, and generates calendar invitations with comprehensive meeting details.

- **pdf**: Intelligently analyze email content and create professional PDF document exports. Removes email metadata, preserves content structure, and generates clean, formatted documents for sharing or archiving.

- **schedule**: Analyze email content to extract scheduling requirements for future or recurring task processing. Creates appropriate cron expressions for reminders, recurring tasks, and future email processing.

- **delete**: Analyze email content to identify and delete scheduled tasks. Handles task ID extraction and provides clear confirmation of task removal.

- **news**: Search for current news and breaking stories with comprehensive analysis and grouping. Provides structured news summaries with source citations, grouped by themes to avoid repetition.
"""

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
