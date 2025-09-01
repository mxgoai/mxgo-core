from enum import Enum
from typing import Any, Union

from pydantic import BaseModel, ConfigDict, Field


class HandlerAlias(str, Enum):
    """Enum for email handle aliases."""

    SUMMARIZE = "summarize"
    RESEARCH = "research"
    SIMPLIFY = "simplify"
    ASK = "ask"
    FACT_CHECK = "fact-check"
    BACKGROUND_RESEARCH = "background-research"
    TRANSLATE = "translate"
    MEETING = "meeting"
    PDF = "pdf"
    SCHEDULE = "schedule"
    DELETE = "delete"
    NEWS = "news"
    UNSUBSCRIBE = "unsubscribe"


class ToolName(str, Enum):
    """Enum for tool names used in email processing."""

    # Common tools available to most handles
    ATTACHMENT_PROCESSOR = "attachment_processor"
    CITATION_AWARE_VISIT = "citation_aware_visit"
    PYTHON_INTERPRETER = "python_interpreter"
    WIKIPEDIA_SEARCH = "wikipedia_search"
    REFERENCES_GENERATOR = "references_generator"
    AZURE_VISUALIZER = "azure_visualizer"

    # Search tools
    DDG_SEARCH = "ddg_search"
    BRAVE_SEARCH = "brave_search"
    GOOGLE_SEARCH = "google_search"
    WEB_SEARCH = "web_search"  # Fallback search tool
    NEWS_SEARCH = "news_search"

    # Specialized tools
    DEEP_RESEARCH = "deep_research"
    MEETING_CREATOR = "meeting_creator"
    PDF_EXPORT = "pdf_export"
    SCHEDULED_TASKS = "scheduled_tasks"
    DELETE_SCHEDULED_TASKS = "delete_scheduled_tasks"

    # External data tools
    LINKEDIN_FRESH_DATA = "linkedin_fresh_data"
    LINKEDIN_DATA_API = "linkedin_data_api"

    # Subscription management tools
    CANCEL_SUBSCRIPTION_TOOL = "cancel_subscription_tool"


# Enum for Rate Limit Plans
class UserPlan(Enum):
    FREE = "free"
    BETA = "beta"
    PRO = "pro"


class EmailAttachment(BaseModel):
    model_config = ConfigDict(validate_default=True)  # Ensure all fields are validated

    filename: str
    contentType: str  # noqa: N815
    contentDisposition: str | None = None  # noqa: N815
    contentId: str | None = None  # noqa: N815
    cid: str | None = None
    content: Union[str, bytes] | None = None  # Can be string (base64) or bytes
    size: int
    path: str | None = None  # Path becomes required after saving to disk

    @property
    def has_valid_content(self) -> bool:
        """Check if the attachment has valid content."""
        return bool(self.content and self.content != "[CONTENT_SAVED_TO_DISK]")

    @property
    def has_valid_path(self) -> bool:
        """Check if the attachment has a valid path."""
        return bool(self.path and self.path.strip())

    @property
    def is_valid(self) -> bool:
        """Check if the attachment is valid - either has content or a valid path."""
        return self.has_valid_content or self.has_valid_path


class EmailRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)  # Allows alias fields

    from_email: str = Field(..., alias="from")
    to: str
    subject: str | None = ""
    rawContent: str | None = ""  # noqa: N815
    recipients: list[str] | None = []
    messageId: str | None = None  # noqa: N815
    date: str | None = None
    inReplyTo: str | None = None  # noqa: N815
    references: str | None = None
    cc: list[str] | None = None
    bcc: str | None = None
    replyTo: str | None = None  # noqa: N815
    returnPath: str | None = None  # noqa: N815
    textContent: str | None = ""  # noqa: N815
    htmlContent: str | None = ""  # noqa: N815
    headers: dict[str, str] | None = {}
    attachments: list[EmailAttachment] | None = []

    rawHeaders: dict[str, Any] | None = None  # noqa: N815
    scheduled_task_id: str | None = None  # ID of scheduled task if this is a scheduled execution
    distilled_processing_instructions: str | None = None  # Processed instructions for the email
    distilled_alias: HandlerAlias | None = (
        None  # Alias to use for processing this email (overrides the detaul to-email handle)
    )
    task_description: str | None = None  # Human-readable description of the scheduled task
    parent_message_id: str | None = None  # Original message ID when this is a scheduled task execution


class ResearchResult(BaseModel):
    """
    Model for email research results.
    """

    query: str = Field(..., description="Research query derived from the email")
    summary: str = Field(..., description="Summary of research findings")
    sources: list[dict[str, Any]] | None = Field(None, description="Sources of information")
    related_topics: list[str] | None = Field(None, description="Related topics identified")


class AttachmentResult(BaseModel):
    """
    Model for attachment processing results.
    """

    filename: str = Field(..., description="Name of the attachment file")
    content_type: str = Field(..., description="Content type of the attachment")
    size_bytes: int = Field(..., description="Size of the attachment in bytes")
    analysis: dict[str, Any] | None = Field(None, description="Analysis of the attachment content")
    error: str | None = Field(None, description="Error message if processing failed")


class EmailProcessingResponse(BaseModel):
    """
    Response model for email processing.
    """

    email_id: str = Field(..., description="Unique ID for the processed email")
    results: dict[str, Any] = Field(..., description="Processing results")
    status: str = Field(..., description="Processing status")


# --- New Schemas for Detailed Email Processing Result ---


class EmailSentStatus(BaseModel):
    status: str
    timestamp: str | None = None
    error: str | None = None
    message_id: str | None = Field(None, alias="MessageId")  # If the key is "MessageId"


class ProcessingError(BaseModel):
    message: str
    details: str | None = None


class ProcessingMetadata(BaseModel):
    processed_at: str
    mode: str | None = None
    errors: list[ProcessingError] = []
    email_sent: EmailSentStatus


class EmailContentDetails(BaseModel):
    html: str | None = None
    text: str | None = None
    enhanced: dict[str, str | None] | None = (
        None  # Retaining dict for simplicity, or could be another EmailContentDetails
    )


class ProcessedAttachmentDetail(BaseModel):
    filename: str
    size: int
    type: str
    error: str | None = None
    caption: str | None = None
    # Add other fields from 'sanitized_att' if they exist, e.g., content summary if stored per attachment


class AttachmentsProcessingResult(BaseModel):
    summary: str | None = None
    processed: list[ProcessedAttachmentDetail] = []


class CalendarResult(BaseModel):
    ics_content: str


class AgentResearchMetadata(BaseModel):
    query: str | None = None
    annotations: list[Any] | None = []  # Define more specific type if known
    visited_urls: list[str] | None = []
    read_urls: list[str] | None = []
    timestamp: str | None = None
    usage: dict[str, Any] | None = {}
    num_urls: int | None = 0


class AgentResearchOutput(BaseModel):
    findings_content: str | None = None  # The main text from research
    metadata: AgentResearchMetadata | None = None


class PDFExportResult(BaseModel):
    """Model for PDF export results."""

    filename: str
    file_path: str
    file_size: int
    title: str
    pages_estimated: int
    mimetype: str = "application/pdf"
    temp_dir: str | None = None  # Path to temp directory for cleanup


class DetailedEmailProcessingResult(BaseModel):
    metadata: ProcessingMetadata
    email_content: EmailContentDetails
    attachments: AttachmentsProcessingResult
    calendar_data: CalendarResult | None = None
    research: AgentResearchOutput | None = None
    pdf_export: PDFExportResult | None = None
    # Add other top-level keys from the agent's result dict if any (e.g. 'summary', 'handle' but they seem to be in error dicts)

    # Ensure Pydantic can populate by name and validate defaults
    model_config = ConfigDict(populate_by_name=True, validate_default=True)


class ProcessingInstructions(BaseModel):
    handle: str
    aliases: list[str]
    process_attachments: bool
    deep_research_mandatory: bool
    allowed_tools: list[ToolName]
    rejection_message: str | None = (
        "This email handle is not supported. Please visit https://mxgo.ai/docs/email-handles to learn about supported email handles."
    )
    task_template: str | None = None
    output_template: str | None = None
    task_specific_instructions: str | None = None
    requires_language_detection: bool = False
    requires_schedule_extraction: bool = False
    target_model: str | None = "gpt-4"
    output_instructions: str | None = None


class LiteLLMParams(BaseModel):
    model: str
    weight: int

    # Traditional API-based model parameters (optional for Bedrock models)
    base_url: str | None = None
    api_key: str | None = None
    api_version: str | None = None

    # AWS Bedrock-specific parameters
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None
    aws_session_token: str | None = None
    aws_region_name: str | None = None
    aws_session_name: str | None = None
    aws_profile_name: str | None = None
    aws_role_name: str | None = None
    aws_web_identity_token: str | None = None
    aws_bedrock_runtime_endpoint: str | None = None
    # Support for Bedrock Application Inference Profile ARNs
    aws_bedrock_inference_profile: str | None = None


class ModelConfig(BaseModel):
    model_name: str
    litellm_params: LiteLLMParams


class RouterConfig(BaseModel):
    routing_strategy: str
    fallbacks: list[dict[str, list[str]]] = []
    default_litellm_params: dict[str, Any]


class CitationSource(BaseModel):
    """A single citation source with metadata."""

    id: str = Field(description="Unique identifier for the citation")
    title: str = Field(description="Title of the source")
    url: str | None = Field(default=None, description="URL of the source")
    filename: str | None = Field(default=None, description="Filename for attachment sources")
    date_accessed: str = Field(description="Date the source was accessed")
    source_type: str = Field(description="Type of source: 'web', 'attachment', 'api'")
    description: str | None = Field(default=None, description="Brief description of the source")


class CitationCollection(BaseModel):
    """Collection of citations with references section."""

    sources: list[CitationSource] = Field(default_factory=list, description="List of citation sources")
    references_section: str = Field(default="", description="Formatted references section")

    def add_source(self, source: CitationSource) -> None:
        """Add a citation source if it doesn't already exist."""
        if not any(s.id == source.id for s in self.sources):
            self.sources.append(source)

    def generate_references_section(self) -> str:  # noqa: PLR0912
        """Generate a formatted references section with improved formatting."""
        if not self.sources:
            return ""

        # Separate visited pages from search results
        visited_sources = []
        search_sources = []
        attachment_sources = []
        api_sources = []

        for source in self.sources:
            if source.source_type == "web":
                if source.description == "visited":
                    visited_sources.append(source)
                else:
                    search_sources.append(source)
            elif source.source_type == "attachment":
                attachment_sources.append(source)
            else:
                api_sources.append(source)

        # Build references section with horizontal line
        references = ["---", "", "### Sources"]

        # Add visited pages first (highest priority)
        if visited_sources:
            references.append("")
            references.append("#### Visited Pages")
            for source in visited_sources:
                ref = f"{source.id}. [{source.title}]({source.url})"
                references.append(ref)

        # Add search results (lower priority, more condensed)
        if search_sources:
            references.append("")
            references.append("#### Search Results")
            for source in search_sources:
                ref = f"{source.id}. [{source.title}]({source.url})"
                references.append(ref)

        # Add attachments
        if attachment_sources:
            references.append("")
            references.append("#### Attachments")
            for source in attachment_sources:
                ref = f"{source.id}. {source.filename}"
                references.append(ref)

        # Add API sources
        if api_sources:
            references.append("")
            references.append("#### Data Sources")
            for source in api_sources:
                ref = f"{source.id}. {source.title}"
                references.append(ref)

        self.references_section = "\n".join(references)
        return self.references_section


class EmailSuggestionAttachmentSummary(BaseModel):
    """Summary of an email attachment for suggestions processing."""

    filename: str
    file_type: str | None = None
    file_size: int


class EmailSuggestionRequest(BaseModel):
    """Request model for email suggestions processing."""

    email_identified: str
    user_email_id: str
    sender_email: str
    cc_emails: list[str]
    subject: str = Field(alias="Subject")
    email_content: str
    attachments: list[EmailSuggestionAttachmentSummary]

    model_config = ConfigDict(populate_by_name=True)


class SuggestionDetail(BaseModel):
    """Details of a single email suggestion."""

    suggestion_title: str
    suggestion_id: str
    suggestion_to_email: str
    suggestion_cc_emails: list[str]
    suggestion_email_instructions: str


class RiskAnalysisResponse(BaseModel):
    """Response model for email risk and spam analysis."""

    risk_prob_pct: int = Field(ge=0, le=100, description="Risk probability percentage (0-100)")
    risk_reason: str = Field(default="", description="Optional one-liner explanation for risk score")
    spam_prob_pct: int = Field(ge=0, le=100, description="Spam probability percentage (0-100)")
    spam_reason: str = Field(default="", description="Optional one-liner explanation for spam score")
    ai_likelihood_pct: int = Field(ge=0, le=100, description="AI authorship likelihood percentage (0-100)")
    ai_explanation: str = Field(default="", description="Brief explanation for AI likelihood (max 25 words)")


class EmailSuggestionResponse(BaseModel):
    """Response model for email suggestions."""

    email_identified: str
    user_email_id: str
    overview: str
    suggestions: list[SuggestionDetail]
    risk_analysis: RiskAnalysisResponse | None = None


class ToolOutputWithCitations(BaseModel):
    """Standard output format for tools that include citations."""

    content: str = Field(description="The main content/result from the tool")
    citations: CitationCollection = Field(default_factory=CitationCollection, description="Collection of citations")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional metadata")


class UsagePeriod(BaseModel):
    """Usage information for a specific time period."""

    period_name: str = Field(description="Time period name (hour, day, month)")
    max_usage_allowed: int = Field(description="Maximum usage allowed for this period")
    current_usage: int = Field(description="Current usage count for this period")


class UsageInfo(BaseModel):
    """User usage information across different time periods."""

    hour: UsagePeriod = Field(description="Hourly usage information")
    day: UsagePeriod = Field(description="Daily usage information")
    month: UsagePeriod = Field(description="Monthly usage information")


class GenerateEmailReplyRequest(BaseModel):
    """Request model for email response generation."""

    email_identified: str
    user_email_id: str
    sender_email: str
    cc_emails: list[str]
    subject: str = Field(alias="Subject")
    email_content: str
    attachments: list[EmailSuggestionAttachmentSummary]
    user_instructions: str = Field(default="", description="Optional user instructions for response generation")

    model_config = ConfigDict(populate_by_name=True)


class ReplyCandidate(BaseModel):
    """A single response candidate with confidence score."""

    response: str = Field(description="The generated response text")
    confidence_pct: int = Field(ge=0, le=100, description="Confidence percentage (0-100)")
    variant: str = Field(description="Type of response variant")
    rationale: str = Field(description="Brief rationale for the response (≤12 words)")


class UserInfoResponse(BaseModel):
    """Response model for user information endpoint."""

    subscription_info: dict[str, Any] = Field(description="Raw subscription info from Dodo Payments API")
    plan_name: str = Field(description="User's plan name (PRO, BETA, etc.)")
    usage_info: UsageInfo = Field(description="User's current usage information")
