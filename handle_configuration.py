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
    target_model: Optional[str] = "gpt-4"  # Default to gpt-4, can be overridden per handle

# Define all email handle configurations
EMAIL_HANDLES = [
    EmailHandleInstructions(
        handle="summarize",
        aliases=["summarise"],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions=None,
        add_summary=True,
        target_model="gpt-4"  # Standard GPT-4 for summarization
    ),
    EmailHandleInstructions(
        handle="simplify",
        aliases=["eli5"],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions=None,
        add_summary=False,  # Direct simplified explanation without summary
        target_model="gpt-4"  # Standard GPT-4 for simplification
    ),
    EmailHandleInstructions(
        handle="ask",
        aliases=["custom", "agent", "assist", "assistant"],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions=None,
        add_summary=True,
        target_model="gpt-4"  # Standard GPT-4 for general assistance
    ),
    EmailHandleInstructions(
        handle="research",
        aliases=["deep-research"],
        process_attachments=True,
        deep_research_mandatory=True,
        specific_research_instructions="Conduct comprehensive research on the email content using all available sources. Return a detailed report with all findings and citations.",
        add_summary=True,
        target_model="gpt-4-reasoning"  # Use reasoning model for deep research
    ),
    EmailHandleInstructions(
        handle="fact-check",
        aliases=[],
        process_attachments=True,
        deep_research_mandatory=True,
        specific_research_instructions="Validate all facts claimed in the email and provide citations from reliable sources",
        add_summary=False,  # Direct fact-checking without summary
        target_model="gpt-4-reasoning"  # Use reasoning model for fact checking
    ),
    EmailHandleInstructions(
        handle="background-research",
        aliases=["background-check"],
        process_attachments=True,
        deep_research_mandatory=True,
        specific_research_instructions="Research identities mentioned in email including names, email addresses, and domains. Focus on finding background information about the sender and other parties mentioned.",
        add_summary=True,
        target_model="gpt-4-reasoning"  # Use reasoning model for background research
    ),
    EmailHandleInstructions(
        handle="translate",
        aliases=[],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions="Detect language if not specified. If non-English, translate to English. If English, look for requested target language or ask user.",
        add_summary=False,  # Direct translation without summary
        target_model="gpt-4"  # Standard GPT-4 for translation
    ),
    EmailHandleInstructions(
        handle="schedule",
        aliases=["schedule-action"],
        process_attachments=True,
        deep_research_mandatory=False,
        specific_research_instructions="Extract meeting/scheduling related information including participants, timing, and location details to provide scheduling recommendations",
        add_summary=True,
        target_model="gpt-4"  # Standard GPT-4 for scheduling
    )
]

# Create a mapping of handles (including aliases) to their configurations
HANDLE_MAP = {}
for config in EMAIL_HANDLES:
    HANDLE_MAP[config.handle] = config
    for alias in config.aliases:
        HANDLE_MAP[alias] = config
