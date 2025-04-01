import asyncio
import json
from pathlib import Path
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.results import Results
from dramatiq.results.backends import RedisBackend

from mxtoai._logging import get_logger
from mxtoai.agents.email_agent import EmailAgent
from mxtoai.config import SKIP_EMAIL_DELIVERY
from mxtoai.email_sender import send_email_reply
from mxtoai.handle_configuration import HANDLE_MAP
from mxtoai.schemas import EmailRequest

logger = get_logger(__name__)

# Initialize Redis broker
redis_broker = RedisBroker(
    url="redis://localhost:6379",
    namespace="dramatiq",
)
redis_backend = RedisBackend(url="redis://localhost:6379", namespace="dramatiq-results")
redis_broker.add_middleware(Results(backend=redis_backend))
dramatiq.set_broker(redis_broker)


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
    email_data: dict[str, Any],
    email_attachments_dir: str,
    attachment_info: list[dict[str, Any]]
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
    processing_result = email_agent.process_email(
        email_request,
        email_instructions
    )

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
                # Run the async function in the sync context
                email_sent_result = asyncio.run(send_email_reply(
                    {
                        "from": email_request.from_email,
                        "to": email_request.to,
                        "subject": email_request.subject,
                        "messageId": email_request.messageId,
                        "references": email_request.references,
                        "cc": email_request.cc
                    },
                    text_content,
                    html_content
                ))

            # Update the email_sent status in metadata
            if "metadata" in processing_result:
                processing_result["metadata"]["email_sent"] = email_sent_result
            else:
                processing_result["metadata"] = {"email_sent": email_sent_result}

    # Log the processing result
    metadata = processing_result.get("metadata", {}).copy()
    if "email_sent" in metadata:
        metadata["email_sent"] = {
            "status": "sent" if metadata["email_sent"] else "failed"
        }
    logger.info(f"Email processed successfully: {json.dumps(metadata)}")

    if email_attachments_dir:
        cleanup_attachments(email_attachments_dir)
