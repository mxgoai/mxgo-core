import json
import os
import shutil
from datetime import datetime
from email.utils import getaddresses
from pathlib import Path
from typing import Annotated, Any, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.security import APIKeyHeader

from mxtoai._logging import get_logger
from mxtoai.agents.email_agent import EmailAgent
from mxtoai.config import ATTACHMENTS_DIR, SKIP_EMAIL_DELIVERY
from mxtoai.dependencies import processing_instructions_resolver
from mxtoai.email_sender import (
    generate_email_id,
    send_email_reply,
)
from mxtoai.schemas import EmailAttachment, EmailRequest
from mxtoai.tasks import process_email_task
from mxtoai.validators import validate_api_key, validate_attachments, validate_email_handle, validate_email_whitelist

# Load environment variables
load_dotenv()

# Configure logging
logger = get_logger(__name__)

MAX_FILENAME_LENGTH = 100

app = FastAPI()
IS_DEV = os.getenv("IS_DEV", "True").lower() == "true"
IS_PROD = os.getenv("IS_PROD", "false").lower() == "true"

if IS_PROD:
    app.openapi_url = None

api_auth_scheme = APIKeyHeader(name="x-api-key", auto_error=True)

# Create the email agent on startup
email_agent = EmailAgent(attachment_dir=ATTACHMENTS_DIR, verbose=True, enable_deep_research=True)


# Function to cleanup attachment files and directory
def cleanup_attachments(directory_path):
    """Delete attachment directory and all its contents"""
    try:
        if Path(directory_path).exists():
            shutil.rmtree(directory_path)
            logger.info(f"Deleted attachment directory: {directory_path}")
        return True
    except Exception as e:
        logger.error(f"Error deleting attachment directory {directory_path}: {e!s}")
        return False
    else:
        return True


def create_success_response(
    summary: str, email_response: dict[str, Any], attachment_info: list[dict[str, Any]]
) -> Response:
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


def _process_single_attachment(
    attachment: EmailAttachment,
    idx: int,
    num_attachments: int,
    email_attachments_dir_path: Path,
    email_data_attachments: list[EmailAttachment] # To append processed attachment info
) -> Optional[dict[str, Any]]:
    """Processes a single attachment: validates, saves, and returns its info."""
    try:
        logger.info(
            f"Processing file {idx + 1}/{num_attachments}: {attachment.filename} ({attachment.content_type})"
        )

        if not attachment.content or len(attachment.content) == 0:
            logger.error(f"Empty content received for file: {attachment.filename}")
            msg = "Empty attachment"
            raise ValueError(msg)

        if attachment.content_type in ["application/x-msdownload", "application/x-executable"]:
            logger.error(f"Unsupported file type: {attachment.content_type}")
            msg = "Unsupported file type"
            raise ValueError(msg)

        safe_filename = Path(attachment.filename).name
        if not safe_filename:
            safe_filename = f"attachment_{idx}.bin"
            logger.warning(f"Using generated filename for attachment {idx}: {safe_filename}")

        if len(safe_filename) > MAX_FILENAME_LENGTH:
            ext = Path(safe_filename).suffix
            safe_filename = (
                safe_filename[: MAX_FILENAME_LENGTH - len(ext) - 5] + "..." + ext
            )
            logger.warning(f"Truncated long filename to: {safe_filename}")

        storage_path = email_attachments_dir_path / safe_filename
        logger.debug(f"Will save file to: {storage_path!s}")

        with storage_path.open("wb") as f:
            f.write(attachment.content)

        if not storage_path.exists():
            logger.error(f"Failed to save attachment: {attachment.filename} to {storage_path!s}")
            return None # Indicate failure

        file_size = storage_path.stat().st_size
        if file_size == 0:
            # Clean up empty file
            storage_path.unlink()
            logger.error(f"Saved file is empty, removed: {storage_path!s}")
            msg = f"Saved file is empty: {storage_path}"
            raise OSError(msg)

        attachment_info_dict = {
            "filename": safe_filename,
            "type": attachment.content_type,
            "path": str(storage_path),
            "size": file_size,
        }

        email_data_attachments.append(
            EmailAttachment(
                filename=safe_filename, content_type=attachment.content_type, size=file_size, path=str(storage_path)
            )
        )
        logger.info(f"Successfully saved attachment: {safe_filename} ({file_size} bytes)")
        return attachment_info_dict

    except ValueError as e: # Specific validation errors
        logger.error(f"Validation error for file {attachment.filename}: {e!s}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception: # General processing error for this attachment
        logger.exception(f"Error processing file {attachment.filename}")
        # Try to clean up any partially saved file if storage_path was defined
        if "storage_path" in locals() and isinstance(storage_path, Path) and storage_path.exists():
            try:
                storage_path.unlink()
                logger.info(f"Cleaned up partial file: {storage_path!s}")
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up partial file: {cleanup_error!s}")
        return None # Indicate failure for this attachment
    else:
        return attachment_info_dict


# Helper function to handle uploaded files
async def handle_file_attachments(
    attachments: list[EmailAttachment], email_id: str, email_data: EmailRequest
) -> tuple[str, list[dict[str, Any]]]:
    """Process uploaded files and save them as attachments"""
    email_attachments_dir_str = ""
    attachment_info_list = []

    if not attachments:
        logger.debug("No files to process")
        return email_attachments_dir_str, attachment_info_list

    email_attachments_dir_path = Path(ATTACHMENTS_DIR) / email_id
    email_attachments_dir_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Created attachments directory: {email_attachments_dir_path!s}")

    # Clear existing attachments from email_data if any, as we are processing new ones.
    email_data.attachments = []

    for idx, attachment_model in enumerate(attachments):
        processed_info = _process_single_attachment(
            attachment=attachment_model,
            idx=idx,
            num_attachments=len(attachments),
            email_attachments_dir_path=email_attachments_dir_path,
            email_data_attachments=email_data.attachments # Pass the list to be modified
        )
        if processed_info:
            attachment_info_list.append(processed_info)

    email_attachments_dir_str = str(email_attachments_dir_path)

    if not attachment_info_list and email_attachments_dir_path.exists():
        logger.warning("No attachments were successfully saved, cleaning up directory")
        shutil.rmtree(email_attachments_dir_path)
        email_attachments_dir_str = ""
    elif attachment_info_list:
        logger.info(f"Successfully processed {len(attachment_info_list)} attachments into {email_attachments_dir_str}")
    else:
        # This case means attachments might have existed, but all failed processing.
        # Directory might still exist if it wasn't empty initially or if rmtree failed (though unlikely here).
        logger.info("No attachments were processed or saved.")
        # If the directory is now empty (because it was created by us and all files failed), clean it up.
        if email_attachments_dir_path.exists() and not any(email_attachments_dir_path.iterdir()):
            logger.info(f"Cleaning up empty attachments directory: {email_attachments_dir_path!s}")
            shutil.rmtree(email_attachments_dir_path)
            email_attachments_dir_str = ""

    return email_attachments_dir_str, attachment_info_list


# Helper function to send email reply using SES
async def send_agent_email_reply(email_data: EmailRequest, processing_result: dict[str, Any]) -> dict[str, Any]:
    """Send email reply using SES and return the response details"""
    if not processing_result or "email_content" not in processing_result:
        logger.error("Invalid processing result format")
        return {
            "status": "error",
            "error": "Invalid processing result format",
            "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
        }

    # Skip email delivery for test emails
    if email_data.from_email in SKIP_EMAIL_DELIVERY:
        logger.info(f"Skipping email delivery for test email: {email_data.from_email}")
        return {
            "status": "skipped",
            "message": "Email delivery skipped for test email",
            "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
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
            "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
        }

    # --- Prepare attachments ---
    attachments_to_send = []
    if processing_result.get("calendar_data") and processing_result["calendar_data"].get("ics_content"):
        ics_content = processing_result["calendar_data"]["ics_content"]
        attachments_to_send.append(
            {
                "filename": "invite.ics",
                "content": ics_content,  # Should be string or bytes
                "mimetype": "text/calendar",
            }
        )
        logger.info("Prepared invite.ics for attachment.")
    # Add logic here if other types of attachments need to be sent back

    # Format the email dict for SES
    ses_email_dict = {
        "from": email_data.from_email,  # Original sender becomes recipient
        "to": email_data.to,  # Original recipient becomes sender
        "subject": email_data.subject,
        "messageId": email_data.messageId,
        "references": email_data.references,
        "inReplyTo": email_data.messageId,
        "cc": email_data.cc,
    }

    try:
        # Log details including CC
        logger.info(
            f"Sending email reply to {ses_email_dict['from']} about '{ses_email_dict['subject']}' with CC: {ses_email_dict.get('cc')}"
        )

        # --- Pass attachments to send_email_reply ---
        reply_result = await send_email_reply(
            original_email=ses_email_dict,
            reply_text=text_content,
            reply_html=html_content,
            attachments=attachments_to_send,  # Pass prepared attachments
        )

        if reply_result.get("status") == "error":
            # Handle specific error from send_email_reply if needed
            logger.error(f"Failed to send email reply: {reply_result.get('error')}")
            # Fall through to return the error response from send_email_reply
        else:
            logger.info(f"Email sent successfully with message ID: {reply_result.get('message_id')}")
        return reply_result

    except Exception as e:
        logger.exception("Error sending email reply")
        return {"status": "error", "error": str(e), "timestamp": datetime.now(datetime.timezone.utc).isoformat()}
    else:
        # This block executes if no exception occurred in the try block
        # It implies reply_result was obtained successfully from await send_email_reply(...)
        if reply_result.get("status") != "error":  # Check status before logging success
            logger.info(f"Email sent successfully with message ID: {reply_result.get('message_id')}")
        return reply_result


# Helper function to create sanitized response
def sanitize_processing_result(processing_result: dict[str, Any]) -> dict[str, Any]:
    """Create a clean response suitable for API return and database storage"""
    if not isinstance(processing_result, dict):
        return {
            "error": "Invalid processing result format",
            "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
        }

    # Start with metadata which is already clean
    sanitized_result = {"metadata": processing_result.get("metadata", {})}

    # Include research if available
    if "research" in processing_result:
        sanitized_result["research"] = processing_result["research"]

    # Include clean attachment info
    if "attachments" in processing_result:
        sanitized_result["attachments"] = {
            "summary": processing_result["attachments"].get("summary"),
            "processed": processing_result["attachments"].get("processed", []),
        }

    # Include email content lengths for monitoring
    if "email_content" in processing_result:
        email_content = processing_result["email_content"]
        sanitized_result["email_content_stats"] = {
            "html_length": len(email_content.get("html", "")) if email_content.get("html") else 0,
            "text_length": len(email_content.get("text", "")) if email_content.get("text") else 0,
            "has_enhanced_content": bool(
                email_content.get("enhanced", {}).get("html") or email_content.get("enhanced", {}).get("text")
            ),
        }

    return sanitized_result


async def _run_initial_validations(
    api_key: str,
    from_email: str,
    to: str,
    subject: Optional[str],
    message_id: Optional[str],
    files: list[UploadFile]
) -> Optional[Response]: # Returns a Response if validation fails, else None
    """Runs all initial validations for the process_email endpoint."""
    if response := await validate_api_key(api_key):
        return response

    # Parse raw headers if provided - This seems to be more related to request creation, moving it there.

    if response := await validate_email_whitelist(from_email, to, subject, message_id):
        return response

    response, handle = await validate_email_handle(to, from_email, subject, message_id)
    if response:
        return response
    # Store handle for later use if needed, or just let it be validated.
    # For now, the handle itself isn't directly used by this validation function beyond its own validation.

    attachments_for_validation = []
    for file_in_list in files:
        content = await file_in_list.read()
        attachments_for_validation.append(
            {"filename": file_in_list.filename, "contentType": file_in_list.content_type, "size": len(content)}
        )
        await file_in_list.seek(0)  # Reset file pointer

    if response := await validate_attachments(attachments_for_validation, from_email, to, subject, message_id):
        return response

    return None # All validations passed


async def _create_email_request_object(
    from_email: str,
    to: str,
    subject: Optional[str],
    text_content: Optional[str],
    html_content: Optional[str],
    message_id: Optional[str],
    date: Optional[str],
    email_id_param: Optional[str], # Renamed to avoid conflict with generated email_id
    raw_headers: Optional[str],
    uploaded_files: list[UploadFile] # For converting to EmailAttachment
) -> EmailRequest:
    """Creates and populates the EmailRequest object."""
    parsed_headers = {}
    if raw_headers:
        try:
            parsed_headers = json.loads(raw_headers)
            logger.info(f"Received raw headers: {json.dumps(parsed_headers, indent=2)}")
        except json.JSONDecodeError:
            logger.warning(f"Could not parse rawHeaders JSON: {raw_headers}")

    cc_list = []
    raw_cc_header = parsed_headers.get("cc", "")
    if isinstance(raw_cc_header, str) and raw_cc_header:
        try:
            addresses = getaddresses([raw_cc_header])
            cc_list = [addr for name, addr in addresses if addr]
            if cc_list:
                logger.info(f"Parsed CC list: {cc_list}")
        except Exception as e:
            logger.warning(f"Could not parse CC header '{raw_cc_header}': {e!s}")

    # Process attachments
    attachments_data = []
    if uploaded_files: # Changed from attachments to uploaded_files to match function signature
        for file_in_list in uploaded_files:
            content = await file_in_list.read()
            attachments_data.append(
                EmailAttachment(
                    filename=file_in_list.filename,
                    content_type=file_in_list.content_type, # Ensure this line is present
                    content=content,
                    size=len(content),
                    path=None, # Explicitly set path to None as it's not available here
                )
            )
            logger.info(f"Prepared EmailAttachment for: {file_in_list.filename}")
            await file_in_list.seek(0) # Reset file pointer

    return EmailRequest(
        from_email=from_email,
        to=to, # Corrected from to_email
        subject=subject,
        raw_content=text_content or html_content or "", # Use raw_content
        text_content=text_content,
        html_content=html_content,
        message_id=message_id,
        date=date,
        email_id=email_id_param,
        raw_headers=parsed_headers,
        cc=cc_list, # Corrected from cc_addresses
        attachments=attachments_data,
        # decoded_attachments was removed as it's not in the schema
    )


def _prepare_attachment_info_for_task(attachment_info_from_handler: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Prepares the attachment information for the task queue."""
    processed_attachment_info_for_task = []
    for info in attachment_info_from_handler:
        processed_info = {
            "filename": info.get("filename", ""),
            "content_type": info.get("type", info.get("content_type", "application/octet-stream")),
            "path": info.get("path", ""),
            "size": info.get("size", 0),
        }
        processed_attachment_info_for_task.append(processed_info)
        logger.info(
            f"Prepared attachment for task: {processed_info['filename']} "
            f"(type: {processed_info['content_type']}, size: {processed_info['size']} bytes)"
        )
    return processed_attachment_info_for_task


@app.post("/process-email")
async def process_email(
    from_email: Annotated[str, Form()],
    to: Annotated[str, Form()],
    api_key: Annotated[str, Depends(api_auth_scheme)],
    subject: Annotated[Optional[str], Form()] = "",
    text_content: Annotated[Optional[str], Form()] = "",
    html_content: Annotated[Optional[str], Form()] = "",
    message_id: Annotated[Optional[str], Form()] = None,
    date: Annotated[Optional[str], Form()] = None,
    email_id: Annotated[Optional[str], Form()] = None,
    raw_headers: Annotated[Optional[str], Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
):
    """Process an incoming email with attachments, analyze content, and send reply"""
    # Validate API key and other initial checks
    if files is None:
        files = [] # Ensure files is a list even if None

    if validation_response := await _run_initial_validations(api_key, from_email, to, subject, message_id, files):
        return validation_response

    # At this point, initial validations have passed.
    # The 'handle' is implicitly validated by _run_initial_validations through validate_email_handle
    # We need to get the handle again for email_instructions or have _run_initial_validations return it.
    # For simplicity, let's re-fetch the handle here, assuming validate_email_handle is idempotent and cheap.
    _, handle = await validate_email_handle(to, from_email, subject, message_id)
    if not handle: # Should not happen if _run_initial_validations passed, but as a safeguard.
        logger.error("Handle could not be determined after successful validation.")
        raise HTTPException(status_code=500, detail="Internal server error: handle determination failed.")

    try:
        email_request = await _create_email_request_object(
            from_email=from_email, to=to, subject=subject,
            text_content=text_content, html_content=html_content,
            message_id=message_id, date=date, email_id_param=email_id, # Pass the original email_id from form
            raw_headers=raw_headers, uploaded_files=files
        )

        # Get handle configuration
        email_instructions = processing_instructions_resolver(handle)  # Safe to use direct access now

        # Log initial email details
        logger.info("Received new email request:")
        logger.info(f"To: {email_request.to} (handle: {handle})") # Use field from email_request
        logger.info(f"Subject: {email_request.subject}")
        logger.info(f"Message ID: {email_request.message_id}")
        logger.info(f"Date: {email_request.date}")
        logger.info(f"Email ID (param): {email_request.email_id}") # Log the passed email_id
        logger.info(f"Number of attachments from request: {len(email_request.attachments)}")
        if email_request.raw_headers:
            logger.info(f"Number of raw headers received: {len(email_request.raw_headers)}")

        # Generate email ID (potentially overriding the one from param if needed, or use the one from param)
        # For now, let's assume the one from param is for tracking and we generate a new one for processing.
        generated_email_id = generate_email_id(email_request) # This uses the content to generate an ID.
        email_request.email_id = generated_email_id # Update request with the truly unique generated ID.
        logger.info(f"Generated/Final email ID for processing: {generated_email_id}")

        # Handle attachments only if the handle requires it
        email_attachments_dir = ""
        attachment_info_for_task = [] # Renamed to avoid confusion with other attachment_info vars
        if email_instructions.process_attachments and email_request.attachments:
            # handle_file_attachments now takes EmailAttachment objects directly
            # It also updates email_request.attachments internally with paths after saving
            email_attachments_dir, attachment_info_for_task = await handle_file_attachments(
                email_request.attachments, # Pass the List[EmailAttachment] from the request object
                generated_email_id, # Use the generated ID for the directory
                email_request # Pass the whole request object for context if needed by handle_file_attachments
            )
            logger.info(f"Processed {len(attachment_info_for_task)} attachments successfully")
            logger.info(f"Attachments directory: {email_attachments_dir}")

        # The attachment_info_for_task from handle_file_attachments is what we need for the task.
        # It contains {"filename", "type", "path", "size"}.
        # This list is already in the correct format for the task, so no further processing needed here.
        # If it needed transformation, we would call _prepare_attachment_info_for_task here.
        # For now, the existing attachment_info_for_task is directly usable.

        # Enqueue the task for async processing
        # Use the attachment_info_for_task directly from handle_file_attachments
        task_attachments = _prepare_attachment_info_for_task(attachment_info_for_task)
        process_email_task.send(email_request.model_dump(), email_attachments_dir, task_attachments)
        logger.info(f"Enqueued email {generated_email_id} for processing with {len(task_attachments)} attachments")

        # Return immediate success response
        return Response(
            content=json.dumps(
                {
                    "message": "Email received and queued for processing",
                    "email_id": generated_email_id,
                    "attachments_saved": len(task_attachments),
                    "status": "processing",
                }
            ),
            status_code=status.HTTP_200_OK,
            media_type="application/json",
        )

    except HTTPException as e:
        # Re-raise HTTPException to maintain the correct status code
        raise e
    except Exception as e:
        # Log the error and clean up
        logger.exception("Error processing email request")

        if "email_attachments_dir" in locals() and email_attachments_dir:
            cleanup_attachments(email_attachments_dir)

        # Return error response
        return Response(
            content=json.dumps(
                {
                    "message": "Error processing email request",
                    "error": str(e),
                    "attachments_saved": len(attachment_info_for_task) if "attachment_info_for_task" in locals() else 0,
                    "attachments_deleted": True,
                }
            ),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            media_type="application/json",
        )


if __name__ == "__main__":
    # Run the server if this file is executed directly
    import uvicorn

    if IS_PROD: # Check against the boolean variable
        logger.info("Production mode detected. Swagger UI disabled.")
        # In a real production scenario, other production-specific configurations
        # like rate limiting or different middleware might be applied here.

    uvicorn.run("mxtoai.api:app", host="0.0.0.0", port=8000, reload=IS_DEV) # Use IS_DEV for reload
