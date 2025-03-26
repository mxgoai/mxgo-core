from pydantic import BaseModel
from typing import Optional, List

class EmailHandleInstructions(BaseModel):
    handle: str
    aliases: List[str]
    process_attachments: bool
    deep_research_mandatory: bool
    specific_research_instructions: Optional[str] = None
    rejection_message: Optional[str] = "This email handle is not supported. Please visit https://mxtoai.com/docs/email-handles to learn about supported email handles."
    task_template: Optional[str] = None
    requires_language_detection: bool = False  # Specifically for translate handle
    requires_schedule_extraction: bool = False  # Specifically for schedule handle
    add_summary: bool = True  # Whether to add a summary section in the response

# Define all email handle configurations
EMAIL_HANDLES = [
    EmailHandleInstructions(
        handle="summarize",
        aliases=["summarise"],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions=None,
        add_summary=True
    ),
    EmailHandleInstructions(
        handle="simplify",
        aliases=["eli5"],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions=None,
        add_summary=False  # Direct simplified explanation without summary
    ),
    EmailHandleInstructions(
        handle="ask",
        aliases=["custom", "agent", "assist", "assistant"],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions=None,
        add_summary=True
    ),
    EmailHandleInstructions(
        handle="research",
        aliases=["deep-research"],
        process_attachments=True,
        deep_research_mandatory=True,
        specific_research_instructions="Conduct comprehensive research on the email content using all available sources",
        add_summary=True
    ),
    EmailHandleInstructions(
        handle="fact-check",
        aliases=[],
        process_attachments=True,
        deep_research_mandatory=True,
        specific_research_instructions="Validate all facts claimed in the email and provide citations from reliable sources",
        add_summary=False  # Direct fact-checking without summary
    ),
    EmailHandleInstructions(
        handle="background-research",
        aliases=["background-check"],
        process_attachments=True,
        deep_research_mandatory=True,
        specific_research_instructions="Research identities mentioned in email including names, email addresses, and domains. Focus on finding background information about the sender and other parties mentioned.",
        add_summary=True
    ),
    EmailHandleInstructions(
        handle="translate",
        aliases=[],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions="Detect language if not specified. If non-English, translate to English. If English, look for requested target language or ask user.",
        add_summary=False  # Direct translation without summary
    ),
    EmailHandleInstructions(
        handle="schedule",
        aliases=["schedule-action"],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions="Extract meeting/scheduling related information including participants, timing, and location details to provide scheduling recommendations",
        add_summary=True
    )
]

# Create a mapping of handles (including aliases) to their configurations
HANDLE_MAP = {}
for config in EMAIL_HANDLES:
    HANDLE_MAP[config.handle] = config
    for alias in config.aliases:
        HANDLE_MAP[alias] = config
