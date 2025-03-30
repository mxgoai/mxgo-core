import asyncio
import json
import os
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from loguru import logger

from mxtoai.agents.email_agent import EmailAgent
from mxtoai.config import SKIP_EMAIL_DELIVERY
from mxtoai.email_sender import send_email_reply
from mxtoai.handle_configuration import HANDLE_MAP
from mxtoai.schemas import EmailRequest

# Initialize Redis broker
redis_broker = RedisBroker(
    url="redis://localhost:6379",
    middleware=[],
    namespace="dramatiq",
    # list_enqueue=True  # Use lists instead of hashes for queues
)
dramatiq.set_broker(redis_broker)

def cleanup_attachments(email_attachments_dir: str) -> None:
    """Clean up attachments after processing."""
    try:
        if os.path.exists(email_attachments_dir):
            for file in os.listdir(email_attachments_dir):
                os.remove(os.path.join(email_attachments_dir, file))
            os.rmdir(email_attachments_dir)
            logger.info(f"Cleaned up attachments directory: {email_attachments_dir}")
    except Exception as e:
        logger.exception(f"Error cleaning up attachments: {e!s}")

@dramatiq.actor
def process_email_task(
    email_data: dict[str, Any],
    email_attachments_dir: str,
    attachment_info: list[dict[str, Any]]
) -> None:
    """
    Dramatiq task for processing emails asynchronously.
    """
    try:
        # Extract handle from email
        handle = email_data["to"].split("@")[0].lower()
        email_instructions = HANDLE_MAP.get(handle)

        if not email_instructions:
            logger.error(f"Unsupported email handle: {handle}")
            return

        # Create EmailRequest instance
        email_request = EmailRequest(**email_data)

        # Initialize EmailAgent (assuming it's thread-safe)
        email_agent = EmailAgent()

        # Enable/disable deep research based on handle configuration
        if email_instructions.deep_research_mandatory:
            email_agent.research_tool.enable_deep_research()
        else:
            email_agent.research_tool.disable_deep_research()

        # Replace the original attachments with processed attachment info
        email_data["attachments"] = attachment_info

        # Process the email
        processing_result = email_agent.process_email(
            email_data,
            email_instructions
        )

        # Send reply email if generated
        if processing_result and "email_content" in processing_result:
            email_content = processing_result["email_content"]
            # Get the enhanced content if available, otherwise use base content
            html_content = email_content.get("enhanced", {}).get("html") or email_content.get("html")
            text_content = email_content.get("enhanced", {}).get("text") or email_content.get("text")

            if text_content:  # Only send if we have at least text content
                # Create email dict for sending reply
                email_dict = {
                    "from": email_request.from_email,
                    "to": email_request.to,
                    "subject": email_request.subject,
                    "messageId": email_request.messageId,
                    "references": email_request.references,
                    "cc": email_request.cc
                }

                # Skip email delivery for test emails
                if email_request.from_email in SKIP_EMAIL_DELIVERY:
                    logger.info(f"Skipping email delivery for test email: {email_request.from_email}")
                    email_sent_result = {"MessageId": "skipped", "status": "skipped"}
                else:
                    # Run the async function in the sync context
                    email_sent_result = asyncio.run(send_email_reply(
                        email_dict,
                        text_content,
                        html_content
                    ))

                # Update the email_sent status in metadata
                if "metadata" in processing_result:
                    processing_result["metadata"]["email_sent"] = email_sent_result
                else:
                    processing_result["metadata"] = {"email_sent": email_sent_result}

        # Log the processing result
        # Only log serializable parts of metadata
        metadata = processing_result.get("metadata", {}).copy()
        if "email_sent" in metadata:
            # Convert email_sent result to a simple status dict
            metadata["email_sent"] = {
                "status": "sent" if metadata["email_sent"] else "failed"
            }
        logger.info(f"Email processed successfully: {json.dumps(metadata)}")

    except Exception as e:
        logger.exception(f"Error in process_email_task: {e!s}")

    finally:
        # Always cleanup attachments
        if email_attachments_dir:
            cleanup_attachments(email_attachments_dir)
