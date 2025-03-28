from fastapi import FastAPI, Response, status, BackgroundTasks, UploadFile, File, Form, HTTPException
import json
import os
import base64
from copy import deepcopy
import shutil
import time
import logging
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Tuple, Any
from dotenv import load_dotenv
from mxtoai.ai import ask_llm
from mxtoai.email import email_sender
from mxtoai.agents.email_agent import EmailAgent
from handle_configuration import HANDLE_MAP
from mxtoai.config import SKIP_EMAIL_DELIVERY
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api")

app = FastAPI()

# Ensure attachments directory exists with absolute path
ATTACHMENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "attachments"))
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)

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
        logger.error(f"Error deleting attachment directory {directory_path}: {str(e)}")
        return False


# Pydantic model for an email attachment
class EmailAttachment(BaseModel):
    filename: str
    contentType: str
    contentDisposition: Optional[str] = None
    contentId: Optional[str] = None
    cid: Optional[str] = None
    content: str  # Base64 encoded content
    size: int


# Pydantic model for the incoming email data
class EmailRequest(BaseModel):
    from_email: str = Field(..., alias="from")
    to: str
    subject: Optional[str] = ""
    rawContent: Optional[str] = ""
    recipients: Optional[List[str]] = []
    messageId: Optional[str] = None
    date: Optional[str] = None
    inReplyTo: Optional[str] = None
    references: Optional[str] = None
    cc: Optional[str] = None
    bcc: Optional[str] = None
    replyTo: Optional[str] = None
    returnPath: Optional[str] = None
    textContent: Optional[str] = ""
    htmlContent: Optional[str] = ""
    headers: Optional[Dict[str, str]] = {}
    attachments: Optional[List[EmailAttachment]] = []
    emailId: Optional[str] = None  # Unique ID for this email

    class Config:
        populate_by_name = True  # Allows alias fields


def log_received_email(email_data: EmailRequest) -> None:
    """Log information about the received email"""
    print("Received email:")
    print(f"From: {email_data.from_email}")
    print(f"Subject: {email_data.subject}")
    print(
        f"Attachments: {len(email_data.attachments) if email_data.attachments else 0}"
    )


def generate_email_id(email_data: EmailRequest) -> str:
    """Generate a unique ID for the email if not provided"""
    return (
        email_data.emailId
        or f"{int(time.time())}-{hash(email_data.from_email + email_data.subject)}"
    )


def save_attachments(email_data: EmailRequest, email_id: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Save attachments from the email and return directory path and attachment info"""
    email_attachments_dir = ""
    attachment_info = []
    
    if not email_data.attachments or len(email_data.attachments) == 0:
        return email_attachments_dir, attachment_info
        
    # Create directory for this email's attachments
    email_attachments_dir = os.path.join(ATTACHMENTS_DIR, email_id)
    os.makedirs(email_attachments_dir, exist_ok=True)

    # Save each attachment
    for idx, attachment in enumerate(email_data.attachments):
        try:
            # Decode base64 content
            try:
                file_content = base64.b64decode(attachment.content)
            except Exception as e:
                logger.error(f"Error decoding base64 content: {str(e)}")
                continue

            # Sanitize filename to avoid path traversal issues
            safe_filename = os.path.basename(attachment.filename)
            if not safe_filename:
                safe_filename = f"attachment_{idx}.bin"

            # Full path to save the attachment
            file_path = os.path.join(email_attachments_dir, safe_filename)

            # Save the file
            with open(file_path, "wb") as f:
                f.write(file_content)

            # Store info about the saved attachment
            attachment_info.append(
                {
                    "filename": safe_filename,
                    "size": attachment.size,
                    "type": attachment.contentType,
                    "path": file_path,
                }
            )

            print(f"Saved attachment: {safe_filename} ({attachment.size} bytes)")
        except Exception as e:
            print(f"Error saving attachment {attachment.filename}: {str(e)}")
            continue
            
    if not attachment_info:
        # If no attachments were successfully saved, clean up the directory
        if os.path.exists(email_attachments_dir):
            shutil.rmtree(email_attachments_dir)
        email_attachments_dir = ""
            
    return email_attachments_dir, attachment_info


def prepare_email_for_ai(email_data: EmailRequest, attachment_info: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Prepare email data for the AI model by removing large attachment content"""
    # Create a copy of the email data
    ai_email_data = deepcopy(email_data)

    # Remove base64 content from attachments to avoid exceeding token limits
    if ai_email_data.attachments:
        for attachment in ai_email_data.attachments:
            # Replace actual content with a placeholder
            attachment.content = f"[CONTENT REMOVED - {attachment.size} bytes]"

    # Convert Pydantic model to dictionary for ask_llm
    # Handle both Pydantic v1 and v2 compatibility
    try:
        # Pydantic v2 approach
        email_dict = ai_email_data.model_dump(by_alias=True)
    except AttributeError:
        # Fallback to Pydantic v1 approach
        email_dict = ai_email_data.dict(by_alias=True)

    # Add processed attachment info
    email_dict["processed_attachments"] = attachment_info
    
    # Format the email data for the agent
    formatted_email = {
        "subject": email_dict.get("subject", ""),
        "body": email_dict.get("textContent", ""),
        "sender": email_dict.get("from", ""),
        "date": email_dict.get("date", ""),
        "attachments": attachment_info
    }
    
    return formatted_email


async def generate_email_summary(email_dict: Dict[str, Any], attachment_info: List[Dict[str, Any]]) -> str:
    """Generate a summary of the email using the AI model"""
    prompt = "Summarise the email"
    if attachment_info:
        prompt += f" and mention that it includes {len(attachment_info)} attachments"

    return await ask_llm(prompt=prompt, email_data=email_dict)


def create_reply_content(summary: str, attachment_info: List[Dict[str, Any]]) -> Tuple[str, str]:
    """Create the text and HTML content for the reply email"""
    # Create plain text reply
    reply_text = f"Here's a summary of your email:\n\n{summary}\n\n"

    # Add info about attachments if any were received
    if attachment_info:
        reply_text += f"We received {len(attachment_info)} attachment(s):\n"
        for att in attachment_info:
            reply_text += f"- {att['filename']} ({att['size']} bytes)\n"

    reply_text += "\nThis is an automated response from the AI assistant."

    # Create HTML version of the reply
    reply_html = f"""
    <div>
        <p>Here's a summary of your email:</p>
        <blockquote style="border-left: 2px solid #ccc; padding-left: 10px; margin-left: 10px;">
            <p>{summary}</p>
        </blockquote>
    """

    # Add attachment info to HTML
    if attachment_info:
        reply_html += f"""
        <p>We received {len(attachment_info)} attachment(s):</p>
        <ul>
        """
        for att in attachment_info:
            reply_html += f"<li>{att['filename']} ({att['size']} bytes)</li>\n"
        reply_html += "</ul>"

    reply_html += """
        <p>This is an automated response from the AI assistant.</p>
    </div>
    """
    
    return reply_text, reply_html


async def send_email_reply(email_dict: Dict[str, Any], reply_text: str, reply_html: str) -> Dict[str, Any]:
    """Send the reply email and return the response"""
    return await email_sender.send_reply(
        original_email=email_dict,
        reply_text=reply_text,
        reply_html=reply_html
    )


def create_success_response(summary: str, email_response: Dict[str, Any], attachment_info: List[Dict[str, Any]]) -> Response:
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


def create_error_response(summary: str, attachment_info: List[Dict[str, Any]], error: str) -> Response:
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
async def handle_file_attachments(files: List[UploadFile], email_id: str, email_data: EmailRequest) -> Tuple[str, List[Dict[str, Any]]]:
    """Process uploaded files and save them as attachments"""
    email_attachments_dir = ""
    attachment_info = []
    
    if not files:
        logger.debug("No files to process")
        return email_attachments_dir, attachment_info
        
    # Create directory for this email's attachments
    email_attachments_dir = os.path.join(ATTACHMENTS_DIR, email_id)
    os.makedirs(email_attachments_dir, exist_ok=True)
    logger.info(f"Created attachments directory: {email_attachments_dir}")
    
    # Process each uploaded file
    for idx, file in enumerate(files):
        try:
            # Log file details
            logger.info(f"Processing file {idx + 1}/{len(files)}: {file.filename} ({file.content_type})")
            
            # Sanitize filename for storage
            safe_filename = os.path.basename(file.filename)
            if not safe_filename:
                safe_filename = f"attachment_{idx}.bin"
                logger.warning(f"Using generated filename for attachment {idx}: {safe_filename}")
            
            # Full path to save the attachment
            storage_path = os.path.join(email_attachments_dir, safe_filename)
            logger.debug(f"Will save file to: {storage_path}")
            
            # Read and save file content
            content = await file.read()
            if not content:
                logger.error(f"Empty content received for file: {file.filename}")
                continue
                
            with open(storage_path, "wb") as f:
                f.write(content)
            
            # Verify file was saved correctly
            if not os.path.exists(storage_path):
                raise IOError(f"Failed to save file: {storage_path}")
            
            file_size = os.path.getsize(storage_path)
            if file_size == 0:
                raise IOError(f"Saved file is empty: {storage_path}")
            
            # Reset file pointer for potential reuse
            await file.seek(0)
            
            # Store attachment info with storage path
            attachment_info.append({
                "filename": safe_filename,
                "size": file_size,
                "type": file.content_type,
                "path": storage_path,  # Use the storage path for processing
            })
            
            logger.info(f"Successfully saved attachment: {safe_filename} ({file_size} bytes)")
            
            # Create EmailAttachment object for compatibility with existing code
            email_data.attachments.append(
                EmailAttachment(
                    filename=safe_filename,
                    contentType=file.content_type,
                    content="[CONTENT_SAVED_TO_DISK]",  # Placeholder since we saved directly to disk
                    size=file_size
                )
            )
            
        except Exception as e:
            logger.error(f"Error processing file {file.filename}: {str(e)}", exc_info=True)
            # Try to clean up any partially saved file
            try:
                storage_path = os.path.join(email_attachments_dir, safe_filename)
                if os.path.exists(storage_path):
                    os.remove(storage_path)
                    logger.info(f"Cleaned up partial file: {storage_path}")
            except Exception as cleanup_error:
                logger.error(f"Error cleaning up partial file: {str(cleanup_error)}")
    
    # If no attachments were successfully saved, clean up the directory
    if not attachment_info and os.path.exists(email_attachments_dir):
        logger.warning("No attachments were successfully saved, cleaning up directory")
        shutil.rmtree(email_attachments_dir)
        email_attachments_dir = ""
    else:
        logger.info(f"Successfully processed {len(attachment_info)} attachments")
            
    return email_attachments_dir, attachment_info


# Helper function to send email reply using SES
async def send_agent_email_reply(email_data: EmailRequest, processing_result: Dict[str, Any]) -> Dict[str, Any]:
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
        logger.error(f"Error sending email reply: {str(e)}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


# Helper function to create sanitized response
def sanitize_processing_result(processing_result: Dict[str, Any]) -> Dict[str, Any]:
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
        print(f"Error sending email reply: {str(e)}")
        
        # Cleanup attachments even on error
        if email_attachments_dir:
            cleanup_attachments(email_attachments_dir)
        
        # Return error response
        return create_error_response(summary, attachment_info, str(e))


@app.post("/process-email")
async def process_email(
    background_tasks: BackgroundTasks,
    from_email: str = Form(...),
    to: str = Form(...),
    subject: Optional[str] = Form(""),
    textContent: Optional[str] = Form(""),
    htmlContent: Optional[str] = Form(""),
    messageId: Optional[str] = Form(None),
    date: Optional[str] = Form(None),
    emailId: Optional[str] = Form(None),
    files: List[UploadFile] = File([]),
):
    """Process an incoming email with attachments, analyze content, and send reply"""
    try:
        # Extract handle from email
        handle = to.split('@')[0].lower()
        
        # Check if handle is supported
        email_instructions = HANDLE_MAP.get(handle)
        if not email_instructions:
            # Send rejection email
            rejection_msg = "This email handle is not supported. Please visit https://mxtoai.com/docs/email-handles to learn about supported email handles."
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

        # Construct email data from form fields
        email_data = EmailRequest(
            from_email=from_email,
            to=to,
            subject=subject,
            textContent=textContent,
            htmlContent=htmlContent,
            messageId=messageId,
            date=date,
            emailId=emailId,
            attachments=[]  # We'll handle attachments separately
        )
        
        # Log the received email and generate ID
        log_received_email(email_data)
        email_id = generate_email_id(email_data)
        
        # Handle attachments only if the handle requires it
        email_attachments_dir = ""
        attachment_info = []
        if email_instructions.process_attachments and files:
            email_attachments_dir, attachment_info = await handle_file_attachments(files, email_id, email_data)
        
        # Prepare email data for AI processing
        email_dict = prepare_email_for_ai(email_data, attachment_info)
        
        # Enable/disable deep research based on handle configuration
        if email_instructions.deep_research_mandatory:
            email_agent.research_tool.enable_deep_research()
        else:
            email_agent.research_tool.disable_deep_research()
        
        # Run the sync agent in a thread pool
        with ThreadPoolExecutor() as pool:
            processing_result = await asyncio.get_event_loop().run_in_executor(
                pool,
                email_agent.process_email,
                email_dict,
                email_instructions  # Pass the entire instructions object instead of just mode
            )
        
        # Send reply email if generated
        if processing_result and "email_content" in processing_result:
            email_sent_result = await send_agent_email_reply(
                email_data, 
                processing_result
            )
            # Update the email_sent status in metadata
            if "metadata" in processing_result:
                processing_result["metadata"]["email_sent"] = email_sent_result
            else:
                processing_result["metadata"] = {"email_sent": email_sent_result}
        
        # Create a clean response without attachment content
        sanitized_result = sanitize_processing_result(processing_result)
        
        # Properly serialize the result to handle any non-serializable objects
        serialized_result = json.loads(json.dumps(sanitized_result, default=lambda o: str(o)))
        
        # Schedule cleanup in the background
        if email_attachments_dir:
            background_tasks.add_task(cleanup_attachments, email_attachments_dir)
        
        # Return success response
        return Response(
            content=json.dumps({
                "message": "Email processed successfully",
                "result": serialized_result,
                "attachments_saved": len(attachment_info),
                "email_sent": processing_result.get("metadata", {}).get("email_sent", {}).get("status") == "success"
            }),
            status_code=status.HTTP_200_OK,
            media_type="application/json",
        )
        
    except Exception as e:
        # Log the error and clean up
        logger.error(f"Error processing email: {str(e)}", exc_info=True)
        
        if 'email_attachments_dir' in locals() and email_attachments_dir:
            cleanup_attachments(email_attachments_dir)
        
        # Return error response
        return Response(
            content=json.dumps({
                "message": "Error processing email",
                "error": str(e),
                "attachments_saved": len(attachment_info) if 'attachment_info' in locals() else 0,
                "attachments_deleted": True,
            }),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            media_type="application/json",
        )


if __name__ == "__main__":
    # Run the server if this file is executed directly
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
