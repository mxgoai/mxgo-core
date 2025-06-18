from enum import Enum  # Added for RateLimitPlan
from typing import Any, Optional, Union, List, Dict

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
    contentDisposition: Optional[str] = None
    contentId: Optional[str] = None
    cid: Optional[str] = None
    content: Optional[Union[str, bytes]] = None  # Can be string (base64) or bytes
    size: int
    path: Optional[str] = None  # Path becomes required after saving to disk

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
    subject: Optional[str] = ""
    rawContent: Optional[str] = ""
    recipients: Optional[list[str]] = []
    messageId: Optional[str] = None
    date: Optional[str] = None
    inReplyTo: Optional[str] = None
    references: Optional[str] = None
    cc: Optional[list[str]] = None
    bcc: Optional[str] = None
    replyTo: Optional[str] = None
    returnPath: Optional[str] = None
    textContent: Optional[str] = ""
    htmlContent: Optional[str] = ""
    headers: Optional[dict[str, str]] = {}
    attachments: Optional[list[EmailAttachment]] = []

    rawHeaders: Optional[dict[str, Any]] = None  # Raw email headers
    scheduled_task_id: Optional[str] = None  # ID of scheduled task if this is a scheduled execution
    distilled_processing_instructions: Optional[str] = None  # Processed instructions for the email
    distilled_alias: Optional[HandlerAlias] = None  # Alias to use for processing this email (overrides the detaul to-email handle)


class ResearchResult(BaseModel):
    """
    Model for email research results.
    """

    query: str = Field(..., description="Research query derived from the email")
    summary: str = Field(..., description="Summary of research findings")
    sources: Optional[list[dict[str, Any]]] = Field(None, description="Sources of information")
    related_topics: Optional[list[str]] = Field(None, description="Related topics identified")


class AttachmentResult(BaseModel):
    """
    Model for attachment processing results.
    """

    filename: str = Field(..., description="Name of the attachment file")
    content_type: str = Field(..., description="Content type of the attachment")
    size_bytes: int = Field(..., description="Size of the attachment in bytes")
    analysis: Optional[dict[str, Any]] = Field(None, description="Analysis of the attachment content")
    error: Optional[str] = Field(None, description="Error message if processing failed")


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
    timestamp: Optional[str] = None
    error: Optional[str] = None
    message_id: Optional[str] = Field(None, alias="MessageId")  # If the key is "MessageId"


class ProcessingError(BaseModel):
    message: str
    details: Optional[str] = None


class ProcessingMetadata(BaseModel):
    processed_at: str
    mode: Optional[str] = None
    errors: list[ProcessingError] = []  # Updated to use ProcessingError model
    email_sent: EmailSentStatus


class EmailContentDetails(BaseModel):
    html: Optional[str] = None
    text: Optional[str] = None
    enhanced: Optional[dict[str, Optional[str]]] = (
        None  # Retaining dict for simplicity, or could be another EmailContentDetails
    )


class ProcessedAttachmentDetail(BaseModel):
    filename: str
    size: int
    type: str
    error: Optional[str] = None
    caption: Optional[str] = None
    # Add other fields from 'sanitized_att' if they exist, e.g., content summary if stored per attachment


class AttachmentsProcessingResult(BaseModel):
    summary: Optional[str] = None
    processed: list[ProcessedAttachmentDetail] = []


class CalendarResult(BaseModel):
    ics_content: str
    # calendar_links: Optional[dict[str, str]] = None # If this exists as per comments in agent


class AgentResearchMetadata(BaseModel):
    query: Optional[str] = None
    annotations: Optional[list[Any]] = []  # Define more specific type if known
    visited_urls: Optional[list[str]] = []
    read_urls: Optional[list[str]] = []
    timestamp: Optional[str] = None
    usage: Optional[dict[str, Any]] = {}
    num_urls: Optional[int] = 0


class AgentResearchOutput(BaseModel):
    findings_content: Optional[str] = None  # The main text from research
    metadata: Optional[AgentResearchMetadata] = None


class PDFExportResult(BaseModel):
    """Model for PDF export results."""

    filename: str
    file_path: str
    file_size: int
    title: str
    pages_estimated: int
    mimetype: str = "application/pdf"
    temp_dir: Optional[str] = None  # Path to temp directory for cleanup


class DetailedEmailProcessingResult(BaseModel):
    metadata: ProcessingMetadata
    email_content: EmailContentDetails
    attachments: AttachmentsProcessingResult
    calendar_data: Optional[CalendarResult] = None
    research: Optional[AgentResearchOutput] = None
    pdf_export: Optional[PDFExportResult] = None
    # Add other top-level keys from the agent's result dict if any (e.g. 'summary', 'handle' but they seem to be in error dicts)

    # Ensure Pydantic can populate by name and validate defaults
    model_config = ConfigDict(populate_by_name=True, validate_default=True)


class ProcessingInstructions(BaseModel):
    handle: str
    aliases: list[str]
    process_attachments: bool
    deep_research_mandatory: bool
    rejection_message: Optional[str] = (
        "This email handle is not supported. Please visit https://mxtoai.com/docs/email-handles to learn about supported email handles."
    )
    task_template: Optional[str] = None
    output_template: Optional[str] = None
    task_specific_instructions: Optional[str] = None
    requires_language_detection: bool = False
    requires_schedule_extraction: bool = False
    target_model: Optional[str] = "gpt-4"
    output_instructions: Optional[str] = None


class LiteLLMParams(BaseModel):
    model: str
    weight: int

    # Traditional API-based model parameters (optional for Bedrock models)
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_version: Optional[str] = None

    # AWS Bedrock-specific parameters
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    aws_region_name: Optional[str] = None
    aws_session_name: Optional[str] = None
    aws_profile_name: Optional[str] = None
    aws_role_name: Optional[str] = None
    aws_web_identity_token: Optional[str] = None
    aws_bedrock_runtime_endpoint: Optional[str] = None
    # Support for Bedrock Application Inference Profile ARNs
    aws_bedrock_inference_profile: Optional[str] = None


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
    url: Optional[str] = Field(default=None, description="URL of the source")
    filename: Optional[str] = Field(default=None, description="Filename for attachment sources")
    date_accessed: str = Field(description="Date the source was accessed")
    source_type: str = Field(description="Type of source: 'web', 'attachment', 'api'")
    description: Optional[str] = Field(default=None, description="Brief description of the source")


class CitationCollection(BaseModel):
    """Collection of citations with references section."""

    sources: List[CitationSource] = Field(default_factory=list, description="List of citation sources")
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
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Additional metadata")
