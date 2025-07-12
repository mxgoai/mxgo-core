from abc import ABC, abstractmethod
import json
from pathlib import Path
from typing import Any

from mxtoai._logging import get_logger
from mxtoai.crud import get_task_by_id
from mxtoai.db import init_db_connection
from mxtoai.prompts.template_prompts import (
    SCHEDULED_TASK_CONTEXT_TEMPLATE,
    SCHEDULED_TASK_ERROR_TEMPLATE,
    SCHEDULED_TASK_NOT_FOUND_TEMPLATE,
)
from mxtoai.request_context import RequestContext
from mxtoai.schemas import EmailRequest, ProcessingInstructions
from mxtoai.scripts.report_formatter import ReportFormatter

logger = get_logger("base_agent")


class BaseAgent(ABC):
    """
    Base class for all email processing agents.
    
    Provides common functionality for email processing including:
    - Request context management
    - Report formatting
    - Attachment directory handling
    - Logging setup
    """

    def __init__(
        self,
        email_request: EmailRequest,
        processing_instructions: ProcessingInstructions,
        attachment_dir: str = "email_attachments",
        *,
        verbose: bool = False,
        attachment_info: list[dict] | None = None,
    ):
        """
        Initialize the base agent with common functionality.

        Args:
            email_request: The email request to process
            processing_instructions: Instructions defining processing configuration
            attachment_dir: Directory to store email attachments
            verbose: Whether to enable verbose logging
            attachment_info: Optional list of attachment info to load into memory
        """
        # Set up logging
        if verbose:
            logger.debug("Verbose logging potentially enabled (actual level depends on logger config).")

        self.email_request = email_request
        self.processing_instructions = processing_instructions
        self.attachment_dir = attachment_dir
        Path(self.attachment_dir).mkdir(parents=True, exist_ok=True)

        # Create request context - this replaces the global citation manager
        self.context = RequestContext(email_request, attachment_info)
        logger.debug("Request context initialized with per-request citation manager")

        # Initialize report formatter (always needed)
        self.report_formatter = ReportFormatter()

        logger.info("Base agent initialized successfully")

    def _finalize_response_with_citations(self, content: str) -> str:
        """
        Finalize the response by appending citations if any were collected.

        Args:
            content: The main response content

        Returns:
            str: Content with appended references section if citations exist
        """
        if self.context.has_citations():
            # Check if content already contains a References or Sources section to avoid duplication
            import re

            existing_references_pattern = r"(^|\n)#{1,3}\s*(References|Sources|Bibliography)\s*$"
            if re.search(existing_references_pattern, content, re.MULTILINE | re.IGNORECASE):
                logger.warning(
                    "Content already contains a References/Sources section - skipping automatic references to avoid duplication"
                )
                return content

            references_section = self.context.get_references_section()
            logger.info(f"Appending references section with {len(self.context.get_citations().sources)} sources")
            return f"{content}\n\n{references_section}"

        logger.debug("No citations found, returning content without references section")
        return content

    def _create_email_context(self, email_request: EmailRequest, attachment_details=None) -> str:
        """
        Generate context information from the email request.

        Args:
            email_request: EmailRequest instance containing email data
            attachment_details: List of formatted attachment details

        Returns:
            str: The context information for the agent
        """
        recipients = ", ".join(email_request.recipients) if email_request.recipients else "N/A"
        attachments_info = (
            f"Available Attachments:\n{chr(10).join(attachment_details)}"
            if attachment_details
            else "No attachments provided."
        )

        email_request_json = email_request.model_dump_json(indent=2)

        # Add scheduled task context if this is a scheduled task execution
        scheduled_context = ""
        if email_request.scheduled_task_id:
            scheduled_context = self._create_scheduled_task_context(email_request.scheduled_task_id)

        base_context = f"""Email Content:
    Subject: {email_request.subject}
    From: {email_request.from_email}
    Email Date: {email_request.date}
    Recipients: {recipients}
    CC: {email_request.cc or "N/A"}
    BCC: {email_request.bcc or "N/A"}
    Body: {email_request.textContent or email_request.htmlContent or ""}

    {attachments_info}

Raw Email Request Data (for tool use):
{email_request_json}"""

        if scheduled_context:
            return f"""{scheduled_context}

{base_context}"""
        return base_context

    def _create_scheduled_task_context(self, scheduled_task_id: str) -> str:
        """
        Create context information for a scheduled task execution.

        Args:
            scheduled_task_id: The ID of the scheduled task being executed

        Returns:
            str: Formatted context explaining this is a scheduled task execution
        """
        try:
            with init_db_connection().get_session() as session:
                # Get the task information using CRUD
                task = get_task_by_id(session, scheduled_task_id)

                if not task:
                    return SCHEDULED_TASK_NOT_FOUND_TEMPLATE.format(scheduled_task_id=scheduled_task_id)

                # Parse the original email request
                try:
                    original_request = (
                        json.loads(task.email_request) if isinstance(task.email_request, str) else task.email_request
                    )
                except (json.JSONDecodeError, TypeError):
                    original_request = {}

                # Format the execution context
                return SCHEDULED_TASK_CONTEXT_TEMPLATE.format(
                    scheduled_task_id=scheduled_task_id,
                    created_at=task.created_at.strftime("%Y-%m-%d %H:%M:%S UTC") if task.created_at else "Unknown",
                    cron_expression=task.cron_expression,
                    original_subject=original_request.get("subject", "Unknown"),
                    original_from=original_request.get("from_email", original_request.get("from", "Unknown")),
                    task_status=task.status,
                )

        except Exception as e:
            logger.error(f"Error creating scheduled task context for {scheduled_task_id}: {e}")
            return SCHEDULED_TASK_ERROR_TEMPLATE.format(scheduled_task_id=scheduled_task_id)

    @abstractmethod
    def process_email(
        self,
        email_request: EmailRequest,
        email_instructions: ProcessingInstructions,
    ) -> Any:
        """
        Process an email using the agent based on the provided email handle instructions.
        
        This method must be implemented by subclasses to define specific processing logic.

        Args:
            email_request: EmailRequest instance containing email data
            email_instructions: ProcessingInstructions object containing processing configuration

        Returns:
            Processing result (type varies by implementation)
        """
        pass
