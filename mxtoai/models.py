from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

class ResearchResult(BaseModel):
    """
    Model for email research results.
    """
    query: str = Field(..., description="Research query derived from the email")
    summary: str = Field(..., description="Summary of research findings")
    sources: Optional[List[Dict[str, Any]]] = Field(None, description="Sources of information")
    related_topics: Optional[List[str]] = Field(None, description="Related topics identified")

class AttachmentResult(BaseModel):
    """
    Model for attachment processing results.
    """
    filename: str = Field(..., description="Name of the attachment file")
    content_type: str = Field(..., description="Content type of the attachment")
    size_bytes: int = Field(..., description="Size of the attachment in bytes")
    analysis: Optional[Dict[str, Any]] = Field(None, description="Analysis of the attachment content")
    error: Optional[str] = Field(None, description="Error message if processing failed")

class EmailProcessingResponse(BaseModel):
    """
    Response model for email processing.
    """
    email_id: str = Field(..., description="Unique ID for the processed email")
    results: Dict[str, Any] = Field(..., description="Processing results")
    status: str = Field(..., description="Processing status") 