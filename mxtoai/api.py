import json
import os
import shutil
from datetime import datetime
from email.utils import getaddresses
from pathlib import Path
from typing import Annotated, Any, Optional

import aiofiles
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Response, UploadFile, status
from fastapi.security import APIKeyHeader

from mxtoai._logging import get_logger
from mxtoai.agents.email_agent import EmailAgent
from mxtoai.config import ATTACHMENTS_DIR, SKIP_EMAIL_DELIVERY
from mxtoai.email_sender import (
    generate_email_id,
    send_email_reply,
)
from mxtoai.handle_configuration import HANDLE_MAP
from mxtoai.schemas import EmailAttachment, EmailRequest
from mxtoai.tasks import process_email_task
from mxtoai.validators import validate_api_key, validate_attachments, validate_email_handle, validate_email_whitelist

# Load environment variables
load_dotenv()

# Configure logging
logger = get_logger(__name__)

app = FastAPI()
if os.environ["IS_PROD"].lower() == "true":
    app.openapi_url = None

api_auth_scheme = APIKeyHeader(name="x-api-key", auto_error=True)

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

    # Create directory for this email's attachments using pathlib
    email_attachments_dir = str(Path(ATTACHMENTS_DIR) / email_id)
    Path(email_attachments_dir).mkdir(parents=True, exist_ok=True)
    logger.info(f"Created attachments directory: {email_attachments_dir}")

    # Process each attachment
    for idx, attachment in enumerate(attachments):
        try:
            # Log file details
            logger.info(f"Processing file {idx + 1}/{len(attachments)}: {attachment.filename} ({attachment.contentType})")

            # Sanitize filename for storage
            safe_filename = Path(attachment.filename).name
            if not safe_filename:
                safe_filename = f"attachment_{idx}.bin"
                logger.warning(f"Using generated filename for attachment {idx}: {safe_filename}")

            # Full path to save the attachment
            storage_path = str(Path(email_attachments_dir) / safe_filename)
            logger.debug(f"Will save file to: {storage_path}")

            # Save the content
            if not attachment.content:
                logger.exception(f"Empty content received for file: {attachment.filename}")
                continue

            # Write content to disk
            async with aiofiles.open(storage_path, "wb") as f:
                await f.write(attachment.content)

            # Verify file was saved correctly
            if not Path(storage_path).exists():
                msg = f"Failed to save file: {storage_path}"
                raise OSError(msg)

            file_size = Path(storage_path).stat().st_size
            if file_size == 0:
                msg = f"Saved file is empty: {storage_path}"
                raise OSError(msg)

            # Store attachment info with storage path
            attachment_info.append({
                "filename": safe_filename,
                "type": attachment.contentType,
                "path": storage_path,
                "size": file_size,
            })

            # Update EmailAttachment object - no need to store content after saving
            email_data.attachments.append(
                EmailAttachment(
                    filename=safe_filename,
                    contentType=attachment.contentType,
                    size=file_size,
                    path=storage_path
                )
            )

            logger.info(f"Successfully saved attachment: {safe_filename} ({file_size} bytes)")

        except Exception as e:
            logger.exception(f"Error processing file {attachment.filename}: {e!s}")
            # Try to clean up any partially saved file
            try:
                if Path(storage_path).exists():
                    Path(storage_path).unlink()
                    logger.info(f"Cleaned up partial file: {storage_path}")
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up partial file: {cleanup_error!s}")

    # If no attachments were successfully saved, clean up the directory
    if not attachment_info and Path(email_attachments_dir).exists():
        logger.warning("No attachments were successfully saved, cleaning up directory")
        import shutil
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

    # Get email body content
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

    # --- Prepare attachments ---
    attachments_to_send = []
    if processing_result.get("calendar_data") and processing_result["calendar_data"].get("ics_content"):
        ics_content = processing_result["calendar_data"]["ics_content"]
        attachments_to_send.append({
            "filename": "invite.ics",
            "content": ics_content, # Should be string or bytes
            "mimetype": "text/calendar"
        })
        logger.info("Prepared invite.ics for attachment.")
    # Add logic here if other types of attachments need to be sent back

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
        # Log details including CC
        logger.info(f"Sending email reply to {ses_email_dict['from']} about '{ses_email_dict['subject']}' with CC: {ses_email_dict.get('cc')}")

        # --- Pass attachments to send_email_reply ---
        email_response = await send_email_reply(
            original_email=ses_email_dict,
            reply_text=text_content,
            reply_html=html_content,
            attachments=attachments_to_send  # Pass prepared attachments
        )

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
    rawHeaders: Annotated[Optional[str], Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
    api_key: str = Depends(api_auth_scheme)
):
    """Process an incoming email with attachments, analyze content, and send reply"""
    # Validate API key
    if response := await validate_api_key(api_key):
        return response

    if files is None:
        files = []
    parsed_headers = {}
    try:
        # Parse raw headers if provided
        if rawHeaders:
            try:
                parsed_headers = json.loads(rawHeaders)
                logger.info(f"Received raw headers: {json.dumps(parsed_headers, indent=2)}")
            except json.JSONDecodeError:
                logger.warning(f"Could not parse rawHeaders JSON: {rawHeaders}")
                # Continue processing even if headers are malformed

        # Validate email whitelist
        if response := await validate_email_whitelist(from_email, to, subject, messageId):
            return response

        # Validate email handle
        response, handle = await validate_email_handle(to, from_email, subject, messageId)
        if response:
            return response

        # Convert uploaded files to dictionaries for validation
        attachments_for_validation = []
        for file in files:
            content = await file.read()
            attachments_for_validation.append({
                "filename": file.filename,
                "contentType": file.content_type,
                "size": len(content)
            })
            await file.seek(0)  # Reset file pointer for later use

        # Validate attachments
        if response := await validate_attachments(attachments_for_validation, from_email, to, subject, messageId):
            return response

        # Convert validated files to EmailAttachment objects
        attachments = []
        for file in files:
            content = await file.read()
            attachments.append(EmailAttachment(
                filename=file.filename,
                contentType=file.content_type,
                content=content,  # Store binary content directly
                size=len(content),
                path=None  # Path will be set after saving to disk
            ))
            logger.info(f"Received attachment: {file.filename} (type: {file.content_type}, size: {len(content)} bytes)")
            await file.seek(0)  # Reset file pointer for later use

        # Get handle configuration
        email_instructions = HANDLE_MAP[handle]  # Safe to use direct access now

        # Log initial email details
        logger.info("Received new email request:")
        logger.info(f"From: {from_email}")
        logger.info(f"To: {to} (handle: {handle})")
        logger.info(f"Subject: {subject}")
        logger.info(f"Message ID: {messageId}")
        logger.info(f"Date: {date}")
        logger.info(f"Email ID: {emailId}")
        logger.info(f"Number of attachments: {len(files)}")
        # Log raw headers count if present
        if parsed_headers:
            logger.info(f"Number of raw headers received: {len(parsed_headers)}")

        # Parse CC addresses from raw headers
        cc_list = []
        raw_cc_header = parsed_headers.get("cc", "")
        if isinstance(raw_cc_header, str) and raw_cc_header:
            try:
                # Use getaddresses to handle names and comma separation
                addresses = getaddresses([raw_cc_header])
                cc_list = [addr for name, addr in addresses if addr]
                if cc_list:
                    logger.info(f"Parsed CC list: {cc_list}")
            except Exception as e:
                logger.warning(f"Could not parse CC header '{raw_cc_header}': {e!s}")

        # Create EmailRequest instance
        email_request = EmailRequest(
            from_email=from_email,
            to=to,
            subject=subject,
            textContent=textContent,
            htmlContent=htmlContent,
            messageId=messageId,
            date=date,
            emailId=emailId,
            rawHeaders=parsed_headers,
            cc=cc_list,
            attachments=[]  # Start with empty list, will be updated after saving files
        )

        # Generate email ID
        email_id = generate_email_id(email_request)
        logger.info(f"Generated email ID: {email_id}")

        # Handle attachments only if the handle requires it
        email_attachments_dir = ""
        attachment_info = []
        if email_instructions.process_attachments and attachments:
            email_attachments_dir, attachment_info = await handle_file_attachments(attachments, email_id, email_request)
            logger.info(f"Processed {len(attachment_info)} attachments successfully")
            logger.info(f"Attachments directory: {email_attachments_dir}")

        # Prepare attachment info for processing
        processed_attachment_info = []
        for info in attachment_info:
            processed_info = {
                "filename": info.get("filename", ""),
                "type": info.get("type", info.get("contentType", "application/octet-stream")),
                "path": info.get("path", ""),
                "size": info.get("size", 0)
            }
            processed_attachment_info.append(processed_info)
            logger.info(f"Prepared attachment for processing: {processed_info['filename']} "
                       f"(type: {processed_info['type']}, size: {processed_info['size']} bytes)")

        # Enqueue the task for async processing
        process_email_task.send(email_request.model_dump(), email_attachments_dir, processed_attachment_info)
        logger.info(f"Enqueued email {email_id} for processing with {len(processed_attachment_info)} attachments")

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
        logger.exception("Error processing email request")

        if "email_attachments_dir" in locals() and email_attachments_dir:
            cleanup_attachments(email_attachments_dir)

        # Return error response
        return Response(
            content=json.dumps({
                "message": "Error processing email request",
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
