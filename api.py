from fastapi import FastAPI, Response, status
import uvicorn
import json
import os
import base64
import copy
import shutil
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from mxtoai.ai import ask_llm
from mxtoai.email import email_sender

app = FastAPI()

# Ensure attachments directory exists
ATTACHMENTS_DIR = "attachments"
os.makedirs(ATTACHMENTS_DIR, exist_ok=True)


# Function to cleanup attachment files and directory
def cleanup_attachments(directory_path):
    """Delete attachment directory and all its contents"""
    try:
        if os.path.exists(directory_path):
            shutil.rmtree(directory_path)
            print(f"Deleted attachment directory: {directory_path}")
        return True
    except Exception as e:
        print(f"Error deleting attachment directory {directory_path}: {str(e)}")
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


@app.post("/process-emails")
async def process_email(email_data: EmailRequest):
    # Log the received email
    print("Received email:")
    print(f"From: {email_data.from_email}")
    print(f"Subject: {email_data.subject}")
    print(
        f"Attachments: {len(email_data.attachments) if email_data.attachments else 0}"
    )

    # Use the provided emailId or generate one if not provided
    email_id = (
        email_data.emailId
        or f"{int(time.time())}-{hash(email_data.from_email + email_data.subject)}"
    )

    # Initialize attachment directory path
    email_attachments_dir = ""

    # Save attachments if any
    attachment_info = []
    if email_data.attachments and len(email_data.attachments) > 0:
        # Create directory for this email's attachments
        email_attachments_dir = os.path.join(ATTACHMENTS_DIR, email_id)
        os.makedirs(email_attachments_dir, exist_ok=True)

        # Save each attachment
        for idx, attachment in enumerate(email_data.attachments):
            try:
                # Decode base64 content
                file_content = base64.b64decode(attachment.content)

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

    # Create a copy of the email data for sending to the AI model
    # without including the large attachment content
    ai_email_data = copy.deepcopy(email_data)

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

    # Process the email with ask_llm
    prompt = "Summarise the email"
    if attachment_info:
        prompt += f" and mention that it includes {len(attachment_info)} attachments"

    summary = await ask_llm(prompt=prompt, email_data=email_dict)

    # Create a reply text with the summary
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

    # Send the reply email
    try:
        # Send the reply
        email_response = await email_sender.send_reply(
            original_email=email_dict, reply_text=reply_text, reply_html=reply_html
        )

        # Delete attachments after successful processing
        if email_attachments_dir:
            cleanup_attachments(email_attachments_dir)

        # Return success response
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
    except Exception as e:
        # Log the error
        print(f"Error sending email reply: {str(e)}")

        # Delete attachments even if there was an error sending the reply
        # since we already have the summary
        if email_attachments_dir:
            cleanup_attachments(email_attachments_dir)

        # Return error response but still include the summary
        return Response(
            content=json.dumps(
                {
                    "message": "Email processed but reply could not be sent",
                    "summary": summary,
                    "attachments_saved": len(attachment_info),
                    "attachments_deleted": True,
                    "error": str(e),
                }
            ),
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            media_type="application/json",
        )


if __name__ == "__main__":
    # Run the server if this file is executed directly
    import uvicorn
    import time
    from dotenv import load_dotenv

    load_dotenv()
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
