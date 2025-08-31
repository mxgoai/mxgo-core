import json
import os
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any

import aiofiles
import redis.asyncio as aioredis
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile, status
from fastapi.security import APIKeyHeader, HTTPBearer
from sqlalchemy import text

from mxgo import user, validators
from mxgo._logging import get_logger
from mxgo.auth import AuthInfo, get_current_user
from mxgo.config import ATTACHMENTS_DIR, RATE_LIMITS_BY_PLAN, SKIP_EMAIL_DELIVERY
from mxgo.db import init_db_connection
from mxgo.dependencies import processing_instructions_resolver
from mxgo.email_sender import (
    generate_email_id,
    send_email_reply,
)
from mxgo.schemas import (
    EmailAttachment,
    EmailRequest,
    EmailSuggestionRequest,
    EmailSuggestionResponse,
    UsageInfo,
    UsagePeriod,
    UserInfoResponse,
    UserPlan,
)
from mxgo.suggestions import generate_suggestions, get_suggestions_model
from mxgo.tasks import process_email_task, rabbitmq_broker
from mxgo.validators import (
    get_current_usage_redis,
    validate_api_key,
    validate_attachments,
    validate_email_handle,
    validate_email_whitelist,
    validate_idempotency,
    validate_rate_limits,
)

# Load environment variables
load_dotenv()

# Redis Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = os.getenv("REDIS_PORT", "6379")
REDIS_DB = os.getenv("REDIS_DB", "0")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

if REDIS_PASSWORD:
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"
else:
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}"


# Constants
MAX_FILENAME_LENGTH = 100
FILENAME_TRUNCATE_BUFFER = 5

# Configure logging
logger = get_logger(__name__)


# Lifespan manager for app startup and shutdown
@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Startup
    logger.info("Application startup: Initializing Redis client for rate limiter...")
    try:
        validators.redis_client = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
        await validators.redis_client.ping()
        logger.info(f"Redis client connected for rate limiting: {REDIS_URL}")
    except Exception as e:
        logger.error(f"Could not connect to Redis for rate limiting at {REDIS_URL}: {e}")
        validators.redis_client = None

    # Load email provider domains
    try:
        current_dir = Path(__file__).parent
        domains_file_path = current_dir / "email_provider_domains.txt"
        if not domains_file_path.exists():
            domains_file_path = Path("mxgo/email_provider_domains.txt")

        if domains_file_path.exists():
            async with aiofiles.open(domains_file_path) as f:
                content = await f.read()
                validators.email_provider_domain_set.update(
                    [line.strip().lower() for line in content.splitlines() if line.strip()]
                )
            logger.info(
                f"Loaded {len(validators.email_provider_domain_set)} email provider domains for rate limit exclusion."
            )
        else:
            logger.warning(
                f"Email provider domains file not found at {domains_file_path}. Domain-specific rate limits might not work as expected."
            )
    except Exception as e:
        logger.error(f"Error loading email provider domains: {e}")

    yield  # Application runs here

    # Shutdown
    logger.info("Application shutdown: Closing Redis client...")
    if validators.redis_client:
        await validators.redis_client.aclose()
        logger.info("Redis client closed.")


app = FastAPI(lifespan=lifespan)
if os.getenv("IS_PROD", "false").lower() == "true":
    app.openapi_url = None

api_auth_scheme = APIKeyHeader(name="x-api-key", auto_error=True)
bearer_auth_scheme = HTTPBearer()


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and load balancers."""
    health_status = {"status": "healthy", "timestamp": datetime.now(timezone.utc).isoformat(), "services": {}}

    overall_healthy = True

    # Check RabbitMQ/Dramatiq broker connection
    try:
        # Try to get broker connection info - this will fail if RabbitMQ is unreachable
        connection_info = rabbitmq_broker.connection
        if connection_info:
            health_status["services"]["rabbitmq"] = "connected"
        else:
            health_status["services"]["rabbitmq"] = "not connected"
            overall_healthy = False
    except Exception as e:
        logger.error(f"RabbitMQ health check failed: {e}")
        health_status["services"]["rabbitmq"] = f"error: {e!s}"
        overall_healthy = False

    # Check database connection
    try:
        db_connection = init_db_connection()
        with db_connection.get_session() as session:
            # Simple query to test connection
            session.execute(text("SELECT 1"))
        health_status["services"]["database"] = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health_status["services"]["database"] = f"error: {e!s}"
        overall_healthy = False

    # Update overall status
    if not overall_healthy:
        health_status["status"] = "unhealthy"

    return health_status


# Function to cleanup attachment files and directory
def cleanup_attachments(directory_path: str) -> bool:
    """
    Delete attachment directory and all its contents

    Args:
        directory_path (str): Path to the directory to be deleted

    Returns:
        bool: True if deletion was successful, False otherwise

    """
    try:
        if Path(directory_path).exists():
            shutil.rmtree(directory_path)
            logger.info(f"Deleted attachment directory: {directory_path}")
    except Exception as e:
        logger.error(f"Error deleting attachment directory {directory_path}: {e!s}")
        return False
    else:
        return True


def create_success_response(
    summary: str, email_response: dict[str, Any], attachment_info: list[dict[str, Any]]
) -> Response:
    """
    Create a success response with summary and email details

    Args:
        summary (str): Summary of the email processing
        email_response (dict): Response from the email sending service
        attachment_info (list): List of processed attachments

    Returns:
        Response: FastAPI Response object with JSON content

    """
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
    """
    Create an error response with summary and error details

    Args:
        summary (str): Summary of the email processing
        attachment_info (list): List of processed attachments
        error (str): Error message

    Returns:
        Response: FastAPI Response object with JSON content

    """
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
async def handle_file_attachments(  # noqa: PLR0912
    attachments: list[EmailAttachment], email_id: str, email_data: EmailRequest
) -> tuple[str, list[dict[str, Any]]]:
    """
    Process uploaded files and save them as attachments

    Args:
        attachments (list[EmailAttachment]): List of EmailAttachment objects
        email_id (str): Unique identifier for the email
        email_data (EmailRequest): EmailRequest object containing email details

    Returns:
        tuple[str, list[dict[str, Any]]]: Tuple containing the directory path and list of processed attachments

    """
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
            logger.info(
                f"Processing file {idx + 1}/{len(attachments)}: {attachment.filename} ({attachment.contentType})"
            )

            # Validate file size
            if not attachment.content or len(attachment.content) == 0:
                logger.error(f"Empty content received for file: {attachment.filename}")
                msg = "Empty attachment"
                raise ValueError(msg)

            # Validate file type
            if attachment.contentType in ["application/x-msdownload", "application/x-executable"]:
                logger.error(f"Unsupported file type: {attachment.contentType}")
                msg = "Unsupported file type"
                raise ValueError(msg)

            # Sanitize filename for storage
            safe_filename = Path(attachment.filename).name
            if not safe_filename:
                safe_filename = f"attachment_{idx}.bin"
                logger.warning(f"Using generated filename for attachment {idx}: {safe_filename}")

            # Truncate filename if too long
            if len(safe_filename) > MAX_FILENAME_LENGTH:
                ext = Path(safe_filename).suffix
                safe_filename = safe_filename[: MAX_FILENAME_LENGTH - FILENAME_TRUNCATE_BUFFER] + ext
                logger.warning(f"Truncated long filename to: {safe_filename}")

            # Full path to save the attachment
            storage_path = str(Path(email_attachments_dir) / safe_filename)
            logger.debug(f"Will save file to: {storage_path}")

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
            attachment_info.append(
                {
                    "filename": safe_filename,
                    "type": attachment.contentType,
                    "path": storage_path,
                    "size": file_size,
                }
            )

            # Update EmailAttachment object - no need to store content after saving
            email_data.attachments.append(
                EmailAttachment(
                    filename=safe_filename, contentType=attachment.contentType, size=file_size, path=storage_path
                )
            )

            logger.info(f"Successfully saved attachment: {safe_filename} ({file_size} bytes)")

        except ValueError as e:
            logger.error(f"Validation error for file {attachment.filename}: {e!s}")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
        except Exception:
            logger.exception(f"Error processing file {attachment.filename}")
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
        shutil.rmtree(email_attachments_dir)
        email_attachments_dir = ""
    else:
        logger.info(f"Successfully processed {len(attachment_info)} attachments")

    return email_attachments_dir, attachment_info


# Helper function to send email reply using SES
async def send_agent_email_reply(email_data: EmailRequest, processing_result: dict[str, Any]) -> dict[str, Any]:
    """
    Send email reply using SES and return the response details

    Args:
        email_data (EmailRequest): EmailRequest object containing email details
        processing_result (dict): Result of the email processing

    Returns:
        dict: Response details including status and message ID

    """
    if not processing_result or "email_content" not in processing_result:
        logger.error("Invalid processing result format")
        return {
            "status": "error",
            "error": "Invalid processing result format",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # Skip email delivery for test emails
    if email_data.from_email in SKIP_EMAIL_DELIVERY:
        logger.info(f"Skipping email delivery for test email: {email_data.from_email}")
        return {
            "status": "skipped",
            "message": "Email delivery skipped for test email",
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
        email_response = await send_email_reply(
            original_email=ses_email_dict,
            reply_text=text_content,
            reply_html=html_content,
            attachments=attachments_to_send,  # Pass prepared attachments
        )

        reply_result = {
            "status": "success",
            "message_id": email_response.get("MessageId", ""),
            "to": ses_email_dict["from"],  # Who we're sending to
            "from": ses_email_dict["to"],  # Who it appears to be from
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info(f"Email sent successfully with message ID: {reply_result['message_id']}")

    except Exception as e:
        logger.exception("Error sending email reply")
        return {"status": "error", "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}
    else:
        return reply_result


# Helper function to create sanitized response
def sanitize_processing_result(processing_result: dict[str, Any]) -> dict[str, Any]:
    """
    Create a clean response suitable for API return and database storage

    Args:
        processing_result (dict): Result of the email processing

    Returns:
        dict: Sanitized response with metadata, research, and attachment info

    """
    if not isinstance(processing_result, dict):
        return {"error": "Invalid processing result format", "timestamp": datetime.now(timezone.utc).isoformat()}

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


def extract_cc_from_headers(headers: dict) -> list[str]:
    cc_val = headers.get("cc")
    if not cc_val:
        return []
    if isinstance(cc_val, str):
        return [addr.strip() for addr in cc_val.split(",") if addr.strip()]
    if isinstance(cc_val, list):
        return [addr for addr in cc_val if isinstance(addr, str) and addr.strip()]
    return []


@app.post("/process-email")
async def process_email(  # noqa: PLR0912, PLR0915
    from_email: Annotated[str, Form()] = ...,
    to: Annotated[str, Form()] = ...,
    subject: Annotated[str | None, Form()] = "",
    textContent: Annotated[str | None, Form()] = "",  # noqa: N803
    htmlContent: Annotated[str | None, Form()] = "",  # noqa: N803
    messageId: Annotated[str | None, Form()] = None,  # noqa: N803
    date: Annotated[str | None, Form()] = None,
    rawHeaders: Annotated[str | None, Form()] = None,  # noqa: N803
    scheduled_task_id: Annotated[str | None, Form()] = None,
    files: Annotated[list[UploadFile] | None, File()] = None,
    api_key: Annotated[str, Depends(api_auth_scheme)] = ...,
):
    """
    Process an incoming email request.

    Args:
        from_email (str): Sender's email address
        to (str): Recipient's email address
        subject (str): Subject of the email
        textContent (str): Plain text content of the email
        htmlContent (str): HTML content of the email
        messageId (str): Unique identifier for the email message
        date (str): Date when the email was sent
        rawHeaders (str): Raw headers of the email in JSON format
        scheduled_task_id (str, optional): ID of the scheduled task if this is a scheduled email
        files (list[UploadFile] | None): List of uploaded files as attachments
        api_key (str): API key for authentication

    Returns:
        JSON response with processing status and details

    """
    # Convert camelCase parameters to snake_case for internal use
    text_content = textContent
    html_content = htmlContent
    message_id = messageId
    raw_headers = rawHeaders

    # Determine if this is a scheduled task
    is_scheduled_task = scheduled_task_id is not None

    if is_scheduled_task:
        logger.info(f"Processing scheduled task: {scheduled_task_id}")

    response = None

    # Skip processing for AWS SES system emails
    if from_email.endswith("@amazonses.com") or ".amazonses.com" in from_email:
        logger.info(f"Skipping processing for AWS SES system email: {from_email} (subject: {subject})")
        logger.info(f"AWS SES email content - Text: {text_content}")
        logger.info(f"AWS SES email content - HTML: {html_content}")
        if raw_headers:
            try:
                parsed_headers = json.loads(raw_headers)
                logger.info(f"AWS SES email headers: {json.dumps(parsed_headers, indent=2)}")
            except json.JSONDecodeError:
                logger.warning(f"Could not parse AWS SES email headers: {raw_headers}")
        response = Response(
            content=json.dumps(
                {
                    "status": "skipped",
                    "message": "AWS SES system email skipped",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ),
            media_type="application/json",
        )
    # Validate API key
    elif response := await validate_api_key(api_key):
        pass  # response already set
    else:
        # Get actual user plan for rate limiting
        try:
            user_plan = await user.get_user_plan(from_email)
        except Exception as e:
            logger.warning(f"Could not determine user plan for {from_email}, falling back to BETA: {e}")
            user_plan = UserPlan.BETA

        # Apply rate limits based on actual user plan
        if response := await validate_rate_limits(from_email, to, subject, message_id, plan=user_plan):
            pass  # response already set
        else:
            # Initialize variables
            parsed_headers = {}
            cc_list = []

            try:
                # Parse raw headers if provided
                if raw_headers:
                    try:
                        parsed_headers = json.loads(raw_headers)
                        logger.info(f"Received raw headers: {json.dumps(parsed_headers, indent=2)}")
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse rawHeaders JSON: {raw_headers}")
                        # Continue processing even if headers are malformed

                # Validate email whitelist
                if response := await validate_email_whitelist(from_email, to, subject, message_id):
                    pass  # response already set
                # Validate email handle
                handle_result = await validate_email_handle(to, from_email, subject, message_id)
                response, handle = handle_result
                if response:
                    pass  # response already set
                # Extract CC list from headers if available
                elif parsed_headers:
                    cc_list = extract_cc_from_headers(parsed_headers)

                # Prepare attachment validation and processing
                attachments_for_validation = []
                email_attachments = []
                if files:
                    # Read file content once and prepare for both validation and processing
                    for file in files:
                        content = await file.read()
                        filename = file.filename or "unknown"
                        content_type = file.content_type or "application/octet-stream"

                        # For validation (dict format)
                        attachments_for_validation.append(
                            {
                                "filename": filename,
                                "contentType": content_type,
                                "content": content,
                                "size": len(content),
                            }
                        )

                        # For processing (EmailAttachment objects)
                        email_attachments.append(
                            EmailAttachment(
                                filename=filename,
                                contentType=content_type,
                                content=content,
                                size=len(content),
                            )
                        )

                # Validate attachments
                if response := await validate_attachments(
                    attachments_for_validation, from_email, to, subject, message_id
                ):
                    pass  # response already set
                else:
                    try:
                        # Check for idempotency (duplicate processing)
                        idempotency_response = await validate_idempotency(
                            from_email=from_email,
                            to=to,
                            subject=subject or "",
                            date=date or "",
                            html_content=html_content or "",
                            text_content=text_content or "",
                            files_count=len(files) if files is not None else 0,
                            message_id=message_id,
                        )
                        if idempotency_response:
                            response_obj, message_id = idempotency_response
                            if response_obj:
                                response = response_obj
                        else:
                            # If validate_idempotency returns None, extract messageId from the tuple
                            _, message_id = idempotency_response

                        if not response:
                            # Log initial email details
                            logger.info("Received new email request:")
                            logger.info(f"To: {to} (handle: {handle})")
                            logger.info(f"Subject: {subject}")
                            logger.info(f"Message ID: {message_id}")
                            logger.info(f"Date: {date}")
                            logger.info(f"Number of attachments: {len(files) if files is not None else 0}")

                            # Create email request object
                            email_request = EmailRequest(
                                from_email=from_email,
                                to=to,
                                subject=subject,
                                textContent=textContent,
                                htmlContent=htmlContent,
                                messageId=message_id,
                                date=date,
                                rawHeaders=parsed_headers,
                                cc=cc_list,
                                attachments=[],  # Start with empty list, will be updated after saving files
                            )

                            # Generate email ID
                            email_id = generate_email_id(email_request)
                            logger.info(f"Generated email ID: {email_id}")

                            # Resolve email instructions for the handle
                            email_instructions = processing_instructions_resolver(handle)

                            # Handle attachments only if the handle requires it
                            email_attachments_dir = ""
                            attachment_info = []
                            if email_instructions.process_attachments and email_attachments:
                                email_attachments_dir, attachment_info = await handle_file_attachments(
                                    email_attachments, email_id, email_request
                                )
                                logger.info(f"Processed {len(attachment_info)} attachments successfully")
                                logger.info(f"Attachments directory: {email_attachments_dir}")

                            # Prepare attachment info for processing
                            processed_attachment_info = []
                            for info in attachment_info:
                                processed_info = {
                                    "filename": info.get("filename", ""),
                                    "type": info.get("type", info.get("contentType", "application/octet-stream")),
                                    "path": info.get("path", ""),
                                    "size": info.get("size", 0),
                                }
                                processed_attachment_info.append(processed_info)
                                logger.info(
                                    f"Prepared attachment for processing: {processed_info['filename']} "
                                    f"(type: {processed_info['type']}, size: {processed_info['size']} bytes)"
                                )

                            # Enqueue the task for async processing
                            process_email_task.send(
                                email_request.model_dump(),
                                email_attachments_dir,
                                processed_attachment_info,
                                scheduled_task_id,
                            )
                            logger.info(
                                f"Enqueued email {email_id} for processing with {len(processed_attachment_info)} attachments"
                                f"{f' (scheduled task: {scheduled_task_id})' if scheduled_task_id else ''}"
                            )

                            # Return success response (always dict, not list)
                            return Response(
                                content=json.dumps(
                                    {
                                        "message": "Email received and queued for processing",
                                        "email_id": email_id,
                                        "attachments_saved": len(processed_attachment_info),
                                        "status": "processing",
                                    }
                                ),
                                status_code=status.HTTP_200_OK,
                                media_type="application/json",
                            )

                    except Exception as e:
                        logger.error(f"Error processing email request: {e}")
                        response = create_error_response(
                            summary="Error processing email",
                            attachment_info=[],
                            error=str(e),
                        )

            except Exception as e:
                logger.error(f"Error in email processing outer block: {e}")
                response = create_error_response(
                    summary="Error processing email",
                    attachment_info=[],
                    error=str(e),
                )

    # At the end of the function, always return a Response object
    if isinstance(response, Response):
        return response
    return Response(
        content=json.dumps(
            {
                "message": "Internal server error: No response generated.",
                "status": "error",
            }
        ),
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        media_type="application/json",
    )


@app.post("/suggestions")
async def process_suggestions(
    requests: list[EmailSuggestionRequest],
    current_user: Annotated[AuthInfo, Depends(get_current_user)] = ...,
    _token: Annotated[str, Depends(bearer_auth_scheme)] = ...,
) -> list[EmailSuggestionResponse]:
    """
    Process a batch of email suggestion requests.

    Args:
        requests: A list of email suggestion requests.
        current_user: The authenticated user from JWT token.

    Returns:
        A list of email suggestion responses.

    """
    # JWT Authentication is handled by dependency injection
    # Get the suggestions model once for all requests
    suggestions_model = get_suggestions_model()

    responses = []

    for request in requests:
        try:
            # Generate suggestions using the suggestions module
            suggestion_response = await generate_suggestions(request, suggestions_model)
            responses.append(suggestion_response)

            logger.info(
                f"Generated {len(suggestion_response.suggestions)} suggestions for email {request.email_identified}"
            )
        except Exception as e:
            logger.error(f"Error processing suggestion request {request.email_identified}: {e}")
            # For other exceptions, raise a generic server error
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error processing suggestion request: {e!s}",
            ) from e

    return responses


@app.get("/user")
async def get_user_info(
    current_user: Annotated[AuthInfo, Depends(get_current_user)] = ...,
    _token: Annotated[str, Depends(bearer_auth_scheme)] = ...,
) -> UserInfoResponse:
    """
    Get user information including subscription, plan, and usage details.

    Args:
        current_user: The authenticated user from JWT token.

    Returns:
        UserInfoResponse: User's subscription info, plan name, and usage information.

    """
    # JWT Authentication is handled by dependency injection
    logger.info(f"JWT authentication successful for user {current_user.email}")

    try:
        # Get user plan
        user_plan = await user.get_user_plan(current_user.email)
        logger.info(f"Retrieved user plan for {current_user.email}: {user_plan.value}")

        # Get customer ID and subscription info
        customer_id = await user._get_customer_id_by_email(current_user.email)  # noqa: SLF001
        subscription_info = {}

        if customer_id:
            subscription_data = await user._get_latest_active_subscription(customer_id)  # noqa: SLF001
            if subscription_data:
                subscription_info = subscription_data
                logger.info(f"Retrieved subscription info for customer {customer_id}")
            else:
                logger.info(f"No active subscription found for customer {customer_id}")
        else:
            logger.info(f"No customer ID found for email {current_user.email}")

        # Get usage information
        normalized_user_email = user.normalize_email(current_user.email)
        current_dt = datetime.now(timezone.utc)

        # Get plan limits configuration
        plan_limits_config = RATE_LIMITS_BY_PLAN.get(user_plan, RATE_LIMITS_BY_PLAN[UserPlan.BETA])

        # Get current usage from Redis
        usage_data = await get_current_usage_redis(
            key_type="email",
            identifier=normalized_user_email,
            plan_or_domain_limits=plan_limits_config,
            current_dt=current_dt,
            plan_name_for_key=user_plan.value,
        )

        # Build usage info response
        usage_periods = {}
        for period_name in ["hour", "day", "month"]:
            period_data = usage_data.get(period_name, {"current_usage": 0, "max_usage_allowed": 0})
            usage_periods[period_name] = UsagePeriod(
                period_name=period_name,
                max_usage_allowed=period_data["max_usage_allowed"],
                current_usage=period_data["current_usage"],
            )

        usage_info = UsageInfo(hour=usage_periods["hour"], day=usage_periods["day"], month=usage_periods["month"])

        logger.info(f"Successfully retrieved user info for {current_user.email}")

        return UserInfoResponse(subscription_info=subscription_info, plan_name=user_plan.value, usage_info=usage_info)

    except Exception as e:
        logger.error(f"Error retrieving user info for {current_user.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving user information: {e!s}",
        ) from e


if __name__ == "__main__":
    # Run the server if this file is executed directly
    import uvicorn

    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=True)
