from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


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
    emailId: Optional[str] = None  # Unique ID for this email
    rawHeaders: Optional[dict[str, Any]] = None  # Raw email headers


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


class DetailedEmailProcessingResult(BaseModel):
    metadata: ProcessingMetadata
    email_content: EmailContentDetails
    attachments: AttachmentsProcessingResult
    calendar_data: Optional[CalendarResult] = None
    research: Optional[AgentResearchOutput] = None
    # Add other top-level keys from the agent's result dict if any (e.g. 'summary', 'handle' but they seem to be in error dicts)

    # Ensure Pydantic can populate by name and validate defaults
    model_config = ConfigDict(populate_by_name=True, validate_default=True)
