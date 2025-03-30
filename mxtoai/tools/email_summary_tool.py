from typing import Optional

from smolagents import Tool

from mxtoai._logging import get_logger

# Configure logger
logger = get_logger("email_summary_tool")

class EmailSummaryTool(Tool):
    """
    Tool for generating concise summaries of emails.
    """

    name = "email_summary"
    description = "Generates a concise summary of an email based on its content."

    inputs = {
        "subject": {
            "type": "string",
            "description": "The email subject"
        },
        "body": {
            "type": "string",
            "description": "The email body content"
        },
        "sender": {
            "type": "string",
            "description": "The email sender"
        },
        "date": {
            "type": "string",
            "description": "The email date"
        },
        "attachment_summary": {
            "type": "string",
            "description": "Optional summary of attachments",
            "nullable": True
        }
    }
    output_type = "string"

    def __init__(self):
        """Initialize the email summary tool."""
        super().__init__()

    def forward(
        self,
        subject: str,
        body: str,
        sender: str,
        date: str,
        attachment_summary: Optional[str] = None
    ) -> str:
        """
        Generate a summary of an email based on its content.

        Args:
            subject: The email subject
            body: The email body
            sender: The email sender
            date: The email date
            attachment_summary: Optional summary of attachments

        Returns:
            A concise summary of the email

        """
        # Format the inputs for the prompt
        prompt_inputs = f"""
        Email Subject: {subject}
        From: {sender}
        Date: {date}

        Body:
        {body}
        """

        if attachment_summary:
            prompt_inputs += f"\n\nAttachments Summary: {attachment_summary}"

        # Generate a summary based on the email content
        # Simple implementation: just return a formatted summary based on the subject and sender
        summary = f"Email from {sender} received on {date} with subject '{subject}'. "

        # Add a brief summary of the content based on the first 100 characters
        content_preview = body[:100] + "..." if len(body) > 100 else body

        summary += f"Content: {content_preview}"

        # Add attachment info if available
        if attachment_summary:
            summary += f" The email includes attachments: {attachment_summary}"

        return summary
