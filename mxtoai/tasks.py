import asyncio
import json
import os
from pathlib import Path
from typing import Any

import dramatiq
from dotenv import load_dotenv
from dramatiq.brokers.rabbitmq import RabbitmqBroker
from dramatiq.results import Results
from dramatiq.results.backends.redis import RedisBackend

from mxtoai._logging import get_logger
from mxtoai.agents.email_agent import EmailAgent
from mxtoai.config import SKIP_EMAIL_DELIVERY
from mxtoai.email_sender import EmailSender
from mxtoai.handle_configuration import HANDLE_MAP
from mxtoai.schemas import EmailRequest

# Load environment variables
load_dotenv()

logger = get_logger(__name__)

# Build RabbitMQ URL from environment variables (Broker)
# Include heartbeat as a query parameter in the URL
RABBITMQ_HEARTBEAT = os.getenv("RABBITMQ_HEARTBEAT", "5")
RABBITMQ_URL = f"amqp://{os.getenv('RABBITMQ_USER', 'guest')}:{os.getenv('RABBITMQ_PASSWORD', 'guest')}@{os.getenv('RABBITMQ_HOST', 'localhost')}:{os.getenv('RABBITMQ_PORT', '5672')}{os.getenv('RABBITMQ_VHOST', '/')}?heartbeat={RABBITMQ_HEARTBEAT}"

# Build Redis URL from environment variables (Results Backend)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_DB = os.getenv("REDIS_DB", "0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")
REDIS_URL = f"redis://{':' + REDIS_PASSWORD + '@' if REDIS_PASSWORD else ''}{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"

# Initialize RabbitMQ broker
rabbitmq_broker = RabbitmqBroker(
    url=RABBITMQ_URL,
    confirm_delivery=True,  # Ensures messages are delivered
    # heartbeat is now part of the URL
)

# Configure Redis as the result backend
redis_backend = RedisBackend(url=REDIS_URL, namespace="dramatiq-results")

# Add results middleware to broker
rabbitmq_broker.add_middleware(Results(backend=redis_backend))
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
    except Exception as e:
        logger.exception(f"Error cleaning up attachments: {e!s}")


def should_retry(retries_so_far, exception):
    logger.warning(f"Retrying task after exception: {exception!s}, retries so far: {retries_so_far}")
    return retries_so_far < 3


@dramatiq.actor(retry_when=should_retry, min_backoff=60 * 1000, time_limit=600000)
def process_email_task(
    email_data: dict[str, Any], email_attachments_dir: str, attachment_info: list[dict[str, Any]]
) -> None:
    """
    Dramatiq task for processing emails asynchronously.

    Args:
        email_data: Dictionary containing email request data
        email_attachments_dir: Directory containing email attachments
        attachment_info: List of attachment information dictionaries

    """
    # Create EmailRequest instance from the dict
    email_request = EmailRequest(**email_data)

    # Extract handle from email
    handle = email_request.to.split("@")[0].lower()
    email_instructions = HANDLE_MAP.get(handle)

    if not email_instructions:
        logger.error(f"Unsupported email handle: {handle}")
        return

    # Initialize EmailAgent
    email_agent = EmailAgent()

    # Enable/disable deep research based on handle configuration
    if email_instructions.deep_research_mandatory:
        email_agent.research_tool.enable_deep_research()
    else:
        email_agent.research_tool.disable_deep_research()

    # Update attachment paths in email_request
    if email_request.attachments and attachment_info:
        valid_attachments = []
        for attachment, info in zip(email_request.attachments, attachment_info, strict=False):
            try:
                # Validate file exists
                if not Path(info["path"]).exists():
                    logger.error(f"Attachment file not found: {info['path']}")
                    continue

                # Update the attachment with file info
                attachment.path = info["path"]
                attachment.contentType = info.get("type") or info.get("contentType") or "application/octet-stream"
                attachment.size = info.get("size", 0)
                valid_attachments.append(attachment)
            except Exception as e:
                logger.error(f"Error processing attachment {attachment.filename}: {e!s}")
                # Continue processing other attachments

        # Update request with only valid attachments
        email_request.attachments = valid_attachments

    # Process the email using the Pydantic model directly
    processing_result = email_agent.process_email(email_request, email_instructions)

    # Send reply email if generated
    if processing_result and "email_content" in processing_result:
        email_content = processing_result["email_content"]
        # Get the enhanced content if available, otherwise use base content
        html_content = email_content.get("enhanced", {}).get("html") or email_content.get("html")
        text_content = email_content.get("enhanced", {}).get("text") or email_content.get("text")

        if text_content:  # Only send if we have at least text content
            # Skip email delivery for test emails
            if email_request.from_email in SKIP_EMAIL_DELIVERY:
                logger.info(f"Skipping email delivery for test email: {email_request.from_email}")
                email_sent_result = {"MessageId": "skipped", "status": "skipped"}
            else:
                # --- Prepare attachments for sending ---
                attachments_to_send = []  # Initialize empty list
                if processing_result.get("calendar_data") and processing_result["calendar_data"].get("ics_content"):
                    ics_content = processing_result["calendar_data"]["ics_content"]
                    attachments_to_send.append(
                        {
                            "filename": "invite.ics",
                            "content": ics_content,  # Should be string or bytes
                            "mimetype": "text/calendar",
                        }
                    )
                    logger.info("Prepared invite.ics for attachment in task.")
                # Add logic here if other types of attachments need to be sent back based on processing_result

                # Define the original email details for clarity
                original_email_details = {
                    "from": email_request.from_email,
                    "to": email_request.to,
                    "subject": email_request.subject,
                    "messageId": email_request.messageId,
                    "references": email_request.references,
                    "cc": email_request.cc,
                }

                # Instantiate EmailSender and call send_reply method
                try:
                    sender = EmailSender()
                    email_sent_result = asyncio.run(
                        sender.send_reply(
                            original_email_details,  # Pass as first positional argument
                            reply_text=text_content,
                            reply_html=html_content,
                            attachments=attachments_to_send,
                        )
                    )
                except Exception as send_err:
                    logger.error(f"Error initializing EmailSender or sending reply: {send_err!s}", exc_info=True)
                    email_sent_result = {"MessageId": "error", "status": "error", "error": str(send_err)}

            # Update the email_sent status in metadata
            if "metadata" in processing_result:
                processing_result["metadata"]["email_sent"] = email_sent_result
            else:
                processing_result["metadata"] = {"email_sent": email_sent_result}

    # Log the processing result
    metadata = processing_result.get("metadata", {}).copy()
    if "email_sent" in metadata:
        metadata["email_sent"] = {"status": "sent" if metadata["email_sent"] else "failed"}
    logger.info(f"Email processed successfully: {json.dumps(metadata)}")

    if email_attachments_dir:
        cleanup_attachments(email_attachments_dir)
