import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

import dramatiq
from dotenv import load_dotenv
from dramatiq.brokers.rabbitmq import RabbitmqBroker

from mxtoai import exceptions  # Import custom exceptions
from mxtoai._logging import get_logger
from mxtoai.agents.email_agent import EmailAgent
from mxtoai.config import SKIP_EMAIL_DELIVERY
from mxtoai.dependencies import processing_instructions_resolver
from mxtoai.email_sender import EmailSender
from mxtoai.models import ProcessingInstructions
from mxtoai.schemas import (
    AttachmentsProcessingResult,
    DetailedEmailProcessingResult,
    EmailContentDetails,
    EmailRequest,
    EmailSentStatus,
    ProcessingError,
    ProcessingMetadata,
)

# Load environment variables
load_dotenv()

logger = get_logger(__name__)

MAX_RETRIES = 3  # Added constant for PLR2004

# Build RabbitMQ URL from environment variables (Broker)
# Include heartbeat as a query parameter in the URL
RABBITMQ_HEARTBEAT = os.getenv("RABBITMQ_HEARTBEAT", "5")
RABBITMQ_URL = f"amqp://{os.getenv('RABBITMQ_USER', 'guest')}:{os.getenv('RABBITMQ_PASSWORD', 'guest')}@{os.getenv('RABBITMQ_HOST', 'localhost')}:{os.getenv('RABBITMQ_PORT', '5672')}{os.getenv('RABBITMQ_VHOST', '/')}?heartbeat={RABBITMQ_HEARTBEAT}"

# Initialize RabbitMQ broker
rabbitmq_broker = RabbitmqBroker(
    url=RABBITMQ_URL,
    confirm_delivery=True,  # Ensures messages are delivered
)
dramatiq.set_broker(rabbitmq_broker)


def cleanup_attachments(email_attachments_dir: str) -> None:
    """Clean up attachments after processing."""
    try:
        dir_path = Path(email_attachments_dir)
        if dir_path.exists():
            for file in dir_path.iterdir():
                try:
                    file.unlink()
                    logger.debug(f"Deleted attachment: {file}")
                except Exception as e:
                    logger.error(f"Failed to delete file {file}: {e!s}")
            dir_path.rmdir()
            logger.info(f"Cleaned up attachments directory: {email_attachments_dir}")
    except Exception:
        logger.exception("Error cleaning up attachments")


def should_retry(retries_so_far, exception):
    logger.warning(f"Retrying task after exception: {exception!s}, retries so far: {retries_so_far}")
    return retries_so_far < MAX_RETRIES


def _resolve_email_instructions(
    handle: str, now_iso: str
) -> Union[tuple[Optional[ProcessingInstructions], None], tuple[None, DetailedEmailProcessingResult]]:
    """Resolves email instructions or returns an error result."""
    try:
        email_instructions: Optional[ProcessingInstructions] = processing_instructions_resolver(handle)
        if not email_instructions: # Should ideally not be hit if resolver raises
            logger.error(f"Unsupported email handle (resolved to None): {handle}")
            error_detail = f"Unsupported email handle (resolved to None): {handle}"
            error_result = DetailedEmailProcessingResult(
                metadata=ProcessingMetadata(
                    processed_at=now_iso, mode=handle, errors=[ProcessingError(message=error_detail)],
                    email_sent=EmailSentStatus(status="error", error=error_detail, timestamp=now_iso)
                ),
                email_content=EmailContentDetails(text=None, html=None, enhanced=None),
                attachments=AttachmentsProcessingResult(processed=[]), calendar_data=None, research=None,
            )
            return None, error_result
    except exceptions.UnspportedHandleException as e:
        logger.error(f"Unsupported email handle: {handle}. Error: {e!s}")
        error_detail = f"Unsupported email handle: {handle} - {e!s}"
        error_result = DetailedEmailProcessingResult(
            metadata=ProcessingMetadata(
                processed_at=now_iso, mode=handle, errors=[ProcessingError(message=f"Unsupported email handle: {handle}", details=str(e))],
                email_sent=EmailSentStatus(status="error", error=error_detail, timestamp=now_iso)
            ),
            email_content=EmailContentDetails(text=None, html=None, enhanced=None),
            attachments=AttachmentsProcessingResult(processed=[]), calendar_data=None, research=None,
        )
        return None, error_result
    else:
        return email_instructions, None

def _configure_agent_research(email_agent: EmailAgent, email_instructions: ProcessingInstructions) -> None:
    """Configures deep research for the email agent."""
    if email_instructions.deep_research_mandatory and email_agent.research_tool:
        email_agent.research_tool.enable_deep_research()
    elif email_agent.research_tool:
        email_agent.research_tool.disable_deep_research()

def _prepare_valid_attachments(email_request: EmailRequest, attachment_info: list[dict[str, Any]]) -> None:
    """Validates and prepares attachments for the email request."""
    if email_request.attachments and attachment_info:
        valid_attachments = []
        # Ensure looping over the shorter of the two lists if lengths mismatch, or handle appropriately.
        # Assuming email_request.attachments and attachment_info correspond by index.
        for i, attachment_model in enumerate(email_request.attachments):
            if i < len(attachment_info):
                info_dict = attachment_info[i]
                try:
                    attachment_path_str = info_dict.get("path")
                    if not attachment_path_str:
                        logger.error(f"Attachment info missing path for {attachment_model.filename}")
                        continue
                    attachment_path = Path(attachment_path_str)
                    if not attachment_path.exists():
                        logger.error(f"Attachment file not found: {attachment_path_str}")
                        continue

                    attachment_model.path = str(attachment_path) # Ensure it's a string
                    attachment_model.contentType = (
                        info_dict.get("type") or info_dict.get("contentType") or "application/octet-stream"
                    )
                    attachment_model.size = info_dict.get("size", 0)
                    valid_attachments.append(attachment_model)
                except Exception as e:
                    logger.error(f"Error processing attachment {attachment_model.filename}: {e!s}")
            else:
                logger.warning(f"Mismatch between attachment models and attachment info for {attachment_model.filename}")
        email_request.attachments = valid_attachments

def _handle_email_sending(processing_result: DetailedEmailProcessingResult, email_request: EmailRequest) -> None:
    """Handles sending the email reply based on processing results."""
    if not (processing_result.email_content and processing_result.email_content.text):
        return # No content to send

    if email_request.from_email in SKIP_EMAIL_DELIVERY:
        logger.info(f"Skipping email delivery for test email: {email_request.from_email}")
        processing_result.metadata.email_sent.status = "skipped"
        processing_result.metadata.email_sent.message_id = "skipped"
        return

    attachments_to_send = []
    if processing_result.calendar_data and processing_result.calendar_data.ics_content:
        attachments_to_send.append({
            "filename": "invite.ics",
            "content": processing_result.calendar_data.ics_content,
            "mimetype": "text/calendar",
        })
        logger.info("Prepared invite.ics for attachment in task.")

    original_email_details = {
        "from": email_request.from_email,
        "to": email_request.to_email, # Assuming EmailRequest has to_email
        "subject": email_request.subject,
        "messageId": email_request.message_id, # Assuming EmailRequest has message_id
        "references": email_request.references, # Assuming EmailRequest has references
        "cc": email_request.cc_addresses, # Assuming EmailRequest has cc_addresses
    }
    try:
        sender = EmailSender()
        email_sent_response = asyncio.run(
            sender.send_reply(
                original_email_details,
                reply_text=processing_result.email_content.text,
                reply_html=processing_result.email_content.html,
                attachments=attachments_to_send,
            )
        )
        processing_result.metadata.email_sent.status = email_sent_response.get("status", "sent")
        processing_result.metadata.email_sent.message_id = email_sent_response.get("MessageId")
        if email_sent_response.get("status") == "error":
            processing_result.metadata.email_sent.error = email_sent_response.get("error", "Unknown send error")
    except Exception as send_err:
        logger.exception("Error initializing EmailSender or sending reply")
        logger.error(f"Email sending error details: {send_err!s}")
        processing_result.metadata.email_sent.status = "error"
        processing_result.metadata.email_sent.error = str(send_err)
        processing_result.metadata.email_sent.message_id = "error"

@dramatiq.actor(retry_when=should_retry, min_backoff=60 * 1000, time_limit=600000)
def process_email_task(
    email_data: dict[str, Any], email_attachments_dir: str, attachment_info: list[dict[str, Any]]
) -> DetailedEmailProcessingResult:
    """
    Dramatiq task for processing emails asynchronously.
    """
    email_request = EmailRequest(**email_data)
    handle = email_request.to_email.split("@")[0].lower() if email_request.to_email else "unknown_handle"
    now_iso = datetime.now(timezone.utc).isoformat()

    email_instructions, error_result = _resolve_email_instructions(handle, now_iso)
    if error_result:
        return error_result
    # email_instructions is guaranteed to be ProcessingInstructions here if error_result is None
    if not email_instructions: # Should not be reached if logic in _resolve_email_instructions is correct
        # Fallback just in case, though _resolve_email_instructions should handle this
        logger.error("Critical: email_instructions is None after _resolve_email_instructions without error_result.")
        # Construct a generic error response here
        return DetailedEmailProcessingResult( metadata=ProcessingMetadata(processed_at=now_iso, mode=handle, errors=[ProcessingError(message="Critical internal error resolving instructions")], email_sent=EmailSentStatus(status="error", error="Internal error", timestamp=now_iso)), email_content=None, attachments=None, calendar_data=None, research=None)

    email_agent = EmailAgent()
    _configure_agent_research(email_agent, email_instructions)
    _prepare_valid_attachments(email_request, attachment_info)

    processing_result = email_agent.process_email(email_request, email_instructions)

    _handle_email_sending(processing_result, email_request)

    try:
        loggable_metadata = processing_result.metadata.model_dump(mode="json")
        logger.info(f"Email processed status: {loggable_metadata.get('email_sent', {}).get('status')}")
    except Exception:
        logger.error("Error serializing processing_result for logging")
        logger.info(f"Email processed. Status: {processing_result.metadata.email_sent.status}")

    if email_attachments_dir:
        cleanup_attachments(email_attachments_dir)

    return processing_result
