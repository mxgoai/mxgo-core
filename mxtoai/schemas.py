from enum import Enum
from typing import Any, Optional, Union

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


# Enum for Rate Limit Plans
class RateLimitPlan(Enum):
    BETA = "beta"


class EmailAttachment(BaseModel):
    model_config = ConfigDict(validate_default=True)  # Ensure all fields are validated

    filename: str
    contentType: str
    contentDisposition: str | None = None
    contentId: str | None = None
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
    rawContent: str | None = ""
    recipients: list[str] | None = []
    messageId: str | None = None
    date: str | None = None
    inReplyTo: str | None = None
    references: str | None = None
    cc: list[str] | None = None
    bcc: str | None = None
    replyTo: str | None = None
    returnPath: str | None = None
    textContent: str | None = ""
    htmlContent: str | None = ""
    headers: dict[str, str] | None = {}
    attachments: list[EmailAttachment] | None = []

    rawHeaders: dict[str, Any] | None = None  # Raw email headers
    scheduled_task_id: str | None = None  # ID of scheduled task if this is a scheduled execution
    distilled_processing_instructions: str | None = None  # Processed instructions for the email
    distilled_alias: HandlerAlias | None = None  # Alias to use for processing this email (overrides the detaul to-email handle)


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
<<<<<<< HEAD
    mode: Optional[str] = None
    errors: list[ProcessingError] = []
=======
    mode: str | None = None
    errors: list[ProcessingError] = []  # Updated to use ProcessingError model
>>>>>>> origin/master
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
    rejection_message: str | None = (
        "This email handle is not supported. Please visit https://mxtoai.com/docs/email-handles to learn about supported email handles."
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
    fallbacks: list[dict[str, list[str]]]
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

    def generate_references_section(self) -> str:
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


class ToolOutputWithCitations(BaseModel):
    """Standard output format for tools that include citations."""

    content: str = Field(description="The main content/result from the tool")
    citations: CitationCollection = Field(default_factory=CitationCollection, description="Collection of citations")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional metadata")
