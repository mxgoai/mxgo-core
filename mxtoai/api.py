import base64
import json
import os
import shutil
from datetime import datetime
from typing import Annotated, Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Response, UploadFile, status

from mxtoai.agents.email_agent import EmailAgent
from mxtoai.config import ATTACHMENTS_DIR, SKIP_EMAIL_DELIVERY
from mxtoai.email_sender import (
    EmailSender as email_sender,
)
from mxtoai.email_sender import (
    create_reply_content,
    generate_email_id,
    generate_email_summary,
    log_received_email,
    prepare_email_for_ai,
    save_attachments,
    send_email_reply,
)
from mxtoai.handle_configuration import HANDLE_MAP
from mxtoai.schemas import EmailAttachment, EmailRequest
from mxtoai.tasks import process_email_task
from mxtoai._logging import get_logger

# Load environment variables
load_dotenv()

# Configure logging
logger = get_logger(__name__)

app = FastAPI()

# Create the email agent on startup
email_agent = EmailAgent(
    attachment_dir=ATTACHMENTS_DIR,
    verbose=True,
    enable_deep_research=True
)


# Function to cleanup attachment files and directory
def cleanup_attachments(directory_path):
    """Delete attachment directory and all its contents"""
    try:
        if os.path.exists(directory_path):
            shutil.rmtree(directory_path)
            logger.info(f"Deleted attachment directory: {directory_path}")
        return True
    except Exception as e:
        logger.error(f"Error deleting attachment directory {directory_path}: {e!s}")
        return False


# Pydantic model for an email attachment


def create_success_response(summary: str, email_response: dict[str, Any], attachment_info: list[dict[str, Any]]) -> Response:
    """Create a success response with summary and email details"""
    return Response(
        content=json.dumps(
            {
                "message": "Email processed and reply sent",
                "summary": summary,
                "email_id": email_response.get("MessageId", ""),
                "attachments_saved": len(attachment_info),
                "attachments_deleted": True,
            }
        ),
        status_code=status.HTTP_200_OK,
        media_type="application/json",
    )


def create_error_response(summary: str, attachment_info: list[dict[str, Any]], error: str) -> Response:
    """Create an error response with summary and error details"""
    return Response(
        content=json.dumps(
            {
                "message": "Email processed but reply could not be sent",
                "summary": summary,
                "attachments_saved": len(attachment_info),
                "attachments_deleted": True,
                "error": str(error),
            }
        ),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        media_type="application/json",
    )


# Helper function to handle uploaded files
async def handle_file_attachments(attachments: list[EmailAttachment], email_id: str, email_data: EmailRequest) -> tuple[str, list[dict[str, Any]]]:
    """Process uploaded files and save them as attachments"""
    email_attachments_dir = ""
    attachment_info = []

    if not attachments:
        logger.debug("No files to process")
        return email_attachments_dir, attachment_info

    # Create directory for this email's attachments
    email_attachments_dir = os.path.join(ATTACHMENTS_DIR, email_id)
    os.makedirs(email_attachments_dir, exist_ok=True)
    logger.info(f"Created attachments directory: {email_attachments_dir}")

    # Process each attachment
    for idx, attachment in enumerate(attachments):
        try:
            # Log file details
            logger.info(f"Processing file {idx + 1}/{len(attachments)}: {attachment.filename} ({attachment.contentType})")

            # Sanitize filename for storage
            safe_filename = os.path.basename(attachment.filename)
            if not safe_filename:
                safe_filename = f"attachment_{idx}.bin"
                logger.warning(f"Using generated filename for attachment {idx}: {safe_filename}")

            # Full path to save the attachment
            storage_path = os.path.join(email_attachments_dir, safe_filename)
            logger.debug(f"Will save file to: {storage_path}")

            # Decode and save file content
            content = base64.b64decode(attachment.content)
            if not content:
                logger.exception(f"Empty content received for file: {attachment.filename}")
                continue

            with open(storage_path, "wb") as f:
                f.write(content)

            # Verify file was saved correctly
            if not os.path.exists(storage_path):
                msg = f"Failed to save file: {storage_path}"
                raise OSError(msg)

            file_size = os.path.getsize(storage_path)
            if file_size == 0:
                msg = f"Saved file is empty: {storage_path}"
                raise OSError(msg)

            # Store attachment info with storage path
            attachment_info.append({
                "filename": safe_filename,
                "type": attachment.contentType,  # Make sure we store the content type
                "path": storage_path,  # Use the storage path for processing
                "size": file_size,
            })

            logger.info(f"Successfully saved attachment: {safe_filename} ({file_size} bytes)")

        except Exception as e:
            logger.exception(f"Error processing file {attachment.filename}: {e!s}")
            # Try to clean up any partially saved file
            try:
                storage_path = os.path.join(email_attachments_dir, safe_filename)
                if os.path.exists(storage_path):
                    os.remove(storage_path)
                    logger.info(f"Cleaned up partial file: {storage_path}")
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up partial file: {cleanup_error!s}")

    # If no attachments were successfully saved, clean up the directory
    if not attachment_info and os.path.exists(email_attachments_dir):
        logger.warning("No attachments were successfully saved, cleaning up directory")
        shutil.rmtree(email_attachments_dir)
        email_attachments_dir = ""
    else:
        logger.info(f"Successfully processed {len(attachment_info)} attachments")

    return email_attachments_dir, attachment_info


# Helper function to send email reply using SES
async def send_agent_email_reply(email_data: EmailRequest, processing_result: dict[str, Any]) -> dict[str, Any]:
    """Send email reply using SES and return the response details"""
    if not processing_result or "email_content" not in processing_result:
        logger.error("Invalid processing result format")
        return {
            "status": "error",
            "error": "Invalid processing result format",
            "timestamp": datetime.now().isoformat()
        }

    # Skip email delivery for test emails
    if email_data.from_email in SKIP_EMAIL_DELIVERY:
        logger.info(f"Skipping email delivery for test email: {email_data.from_email}")
        return {
            "status": "skipped",
            "message": "Email delivery skipped for test email",
            "timestamp": datetime.now().isoformat()
        }

    # Get the enhanced content if available, otherwise use base content
    email_content = processing_result["email_content"]
    html_content = email_content.get("enhanced", {}).get("html") or email_content.get("html")
    text_content = email_content.get("enhanced", {}).get("text") or email_content.get("text")

    # Handle case where no content was generated
    if not text_content:
        logger.error("No email content was generated")
        return {
            "status": "error",
            "error": "No email content was generated",
            "timestamp": datetime.now().isoformat()
        }

    # Format the email dict for SES
    ses_email_dict = {
        "from": email_data.from_email,  # Original sender becomes recipient
        "to": email_data.to,            # Original recipient becomes sender
        "subject": email_data.subject,
        "messageId": email_data.messageId,
        "references": email_data.references,
        "inReplyTo": email_data.messageId,
        "cc": email_data.cc
    }

    try:
        logger.info(f"Sending email reply to {ses_email_dict['from']} about '{ses_email_dict['subject']}'")
        email_response = await send_email_reply(ses_email_dict, text_content, html_content)

        reply_result = {
            "status": "success",
            "message_id": email_response.get("MessageId", ""),
            "to": ses_email_dict["from"],  # Who we're sending to
            "from": ses_email_dict["to"],  # Who it appears to be from
            "timestamp": datetime.now().isoformat()
        }

        logger.info(f"Email sent successfully with message ID: {reply_result['message_id']}")
        return reply_result

    except Exception as e:
        logger.error(f"Error sending email reply: {e!s}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# Helper function to create sanitized response
def sanitize_processing_result(processing_result: dict[str, Any]) -> dict[str, Any]:
    """Create a clean response suitable for API return and database storage"""
    if not isinstance(processing_result, dict):
        return {
            "error": "Invalid processing result format",
            "timestamp": datetime.now().isoformat()
        }

    # Start with metadata which is already clean
    sanitized_result = {
        "metadata": processing_result.get("metadata", {})
    }

    # Include research if available
    if "research" in processing_result:
        sanitized_result["research"] = processing_result["research"]

    # Include clean attachment info
    if "attachments" in processing_result:
        sanitized_result["attachments"] = {
            "summary": processing_result["attachments"].get("summary"),
            "processed": processing_result["attachments"].get("processed", [])
        }

    # Include email content lengths for monitoring
    if "email_content" in processing_result:
        email_content = processing_result["email_content"]
        sanitized_result["email_content_stats"] = {
            "html_length": len(email_content.get("html", "")) if email_content.get("html") else 0,
            "text_length": len(email_content.get("text", "")) if email_content.get("text") else 0,
            "has_enhanced_content": bool(email_content.get("enhanced", {}).get("html") or email_content.get("enhanced", {}).get("text"))
        }

    return sanitized_result


@app.post("/process-emails")
async def process_emails(email_data: EmailRequest):
    """Process an incoming email, save attachments, generate summary, and send reply"""
    # Step 1: Log the received email
    log_received_email(email_data)

    # Step 2: Generate or use the provided email ID
    email_id = generate_email_id(email_data)

    # Step 3: Save attachments if any
    email_attachments_dir, attachment_info = save_attachments(email_data, email_id)

    # Step 4: Prepare email data for AI processing
    email_dict = prepare_email_for_ai(email_data, attachment_info)

    # Step 5: Generate email summary using AI
    summary = await generate_email_summary(email_dict, attachment_info)

    # Step 6: Create reply content (text and HTML)
    reply_text, reply_html = create_reply_content(summary, attachment_info)

    # Step 7: Send the reply email
    try:
        email_response = await send_email_reply(email_dict, reply_text, reply_html)

        # Step 8: Cleanup attachments after successful processing
        if email_attachments_dir:
            cleanup_attachments(email_attachments_dir)

        # Step 9: Return success response
        return create_success_response(summary, email_response, attachment_info)

    except Exception as e:
        # Log the error

        # Cleanup attachments even on error
        if email_attachments_dir:
            cleanup_attachments(email_attachments_dir)

        # Return error response
        return create_error_response(summary, attachment_info, str(e))


@app.post("/process-email")
async def process_email(
    from_email: Annotated[str, Form()] = ...,
    to: Annotated[str, Form()] = ...,
    subject: Annotated[Optional[str], Form()] = "",
    textContent: Annotated[Optional[str], Form()] = "",
    htmlContent: Annotated[Optional[str], Form()] = "",
    messageId: Annotated[Optional[str], Form()] = None,
    date: Annotated[Optional[str], Form()] = None,
    emailId: Annotated[Optional[str], Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
):
    """Process an incoming email with attachments, analyze content, and send reply"""
    if files is None:
        files = []
    try:
        # Extract handle from email
        handle = to.split("@")[0].lower()

        # Check if handle is supported
        email_instructions = HANDLE_MAP.get(handle)
        if not email_instructions:
            # Send rejection email
            rejection_msg = "This email alias is not supported. Please visit https://mxtoai.com/docs/email-handles to learn about supported email handles."
            await email_sender.send_reply(
                {
                    "from": from_email,
                    "to": to,
                    "subject": f"Re: {subject}",
                    "messageId": messageId,
                },
                rejection_msg,
                rejection_msg
            )
            return Response(
                content=json.dumps({
                    "message": "Unsupported email handle",
                    "handle": handle,
                    "rejection_sent": True
                }),
                status_code=status.HTTP_400_BAD_REQUEST,
                media_type="application/json",
            )

        # Convert uploaded files to EmailAttachment objects
        attachments = []
        for file in files:
            content = await file.read()
            attachments.append(EmailAttachment(
                filename=file.filename,
                contentType=file.content_type,
                content=base64.b64encode(content).decode(),
                size=len(content)
            ))
            await file.seek(0)  # Reset file pointer for later use

        # Construct email data from form fields
        email_data = {
            "from_email": from_email,
            "to": to,
            "subject": subject,
            "textContent": textContent,
            "htmlContent": htmlContent,
            "messageId": messageId,
            "date": date,
            "emailId": emailId,
            "attachments": [att.model_dump() for att in attachments]  # Convert each attachment to dict
        }

        email_request = EmailRequest(**email_data)

        # Log the received email and generate ID
        log_received_email(email_request)
        email_id = generate_email_id(email_request)

        # Handle attachments only if the handle requires it
        email_attachments_dir = ""
        attachment_info = []
        if email_instructions.process_attachments and attachments:
            email_attachments_dir, attachment_info = await handle_file_attachments(attachments, email_id, email_request)

        # Prepare attachment info for processing
        processed_attachment_info = []
        for info in attachment_info:
            processed_attachment_info.append({
                "filename": info.get("filename", ""),
                "type": info.get("type", info.get("contentType", "application/octet-stream")),  # Fallback to contentType or default
                "path": info.get("path", ""),  # This should be set during handle_file_attachments
                "size": info.get("size", 0)
            })

        # Enqueue the task for async processing
        process_email_task.send(email_data, email_attachments_dir, processed_attachment_info)

        # Return immediate success response
        return Response(
            content=json.dumps({
                "message": "Email received and queued for processing",
                "email_id": email_id,
                "attachments_saved": len(attachment_info),
                "status": "processing"
            }),
            status_code=status.HTTP_200_OK,
            media_type="application/json",
        )

    except Exception as e:
        # Log the error and clean up
        logger.error(f"Error queueing email: {e!s}", exc_info=True)

        if "email_attachments_dir" in locals() and email_attachments_dir:
            cleanup_attachments(email_attachments_dir)

        # Return error response
        return Response(
            content=json.dumps({
                "message": "Error queueing email for processing",
                "error": str(e),
                "attachments_saved": len(attachment_info) if "attachment_info" in locals() else 0,
                "attachments_deleted": True,
            }),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            media_type="application/json",
        )


if __name__ == "__main__":
    # Run the server if this file is executed directly
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
