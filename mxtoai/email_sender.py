import base64
import os
import time
from copy import deepcopy
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from mxtoai._logging import get_logger
from mxtoai.config import ATTACHMENTS_DIR
from mxtoai.schemas import EmailRequest

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger("mxtoai.email")

class EmailSender:
    """
    Class to handle sending emails via AWS SES, including replies to original emails.
    """

    def __init__(self):
        """
        Initialize the AWS SES client.
        """
        # AWS SES client configuration
        region = os.getenv("AWS_REGION", "us-east-1")
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        session_token = os.getenv("AWS_SESSION_TOKEN")

        # Validate required credentials
        if not access_key or not secret_key:
            logger.error("AWS credentials missing: Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            msg = "AWS credentials missing"
            raise ValueError(msg)

        # Build SES config

        # Try different ways to initialize the client until one works
        self.ses_client = None
        errors = []

        # Method 1: Use explicit credentials
        try:
            logger.info(f"Attempting to initialize SES client with explicit credentials in region {region}")
            self.ses_client = boto3.client(
                "ses",
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                **({"aws_session_token": session_token} if session_token else {})
            )
            # Test connection
            self.ses_client.get_send_quota()
            logger.info("SES client initialized successfully with explicit credentials")
        except Exception as e:
            errors.append(f"Method 1 failed: {e!s}")
            self.ses_client = None

        # If all methods failed, raise an exception with details
        if not self.ses_client:
            error_details = "\n".join(errors)
            logger.error(f"Failed to initialize SES client after all attempts:\n{error_details}")
            msg = f"Could not connect to AWS SES: {error_details}"
            raise ConnectionError(msg)

        self.default_sender_email = os.getenv("SENDER_EMAIL", "ai-assistant@mxtoai.com")
        logger.info(f"EmailSender initialized with default sender: {self.default_sender_email}")

    async def send_email(
        self,
        to_address: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        cc_addresses: Optional[list[str]] = None,
        reply_to_addresses: Optional[list[str]] = None,
        sender_email: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Send an email using AWS SES.
        """
        try:
            # Use provided sender_email or fall back to default
            source_email = sender_email or self.default_sender_email

            message = {
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": body_text}}
            }

            if body_html:
                message["Body"]["Html"] = {"Data": body_html}

            email_params = {
                "Source": source_email,
                "Destination": {"ToAddresses": [to_address]},
                "Message": message
            }

            if cc_addresses:
                email_params["Destination"]["CcAddresses"] = cc_addresses

            if reply_to_addresses:
                email_params["ReplyToAddresses"] = reply_to_addresses

            logger.info(f"Sending email from {source_email} to {to_address} with subject: {subject}")
            response = self.ses_client.send_email(**email_params)
            logger.info(f"Email sent successfully: {response['MessageId']}")
            return response

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "MessageRejected":
                logger.error(f"Email rejected: {error_message}")
                if "Email address is not verified" in error_message:
                    logger.error(f"The sender email '{source_email}' is not verified in SES. "
                                f"Verify it in the AWS SES console or use a different verified email.")
            elif error_code == "SignatureDoesNotMatch":
                logger.error(f"AWS authentication failed: {error_message}")
                logger.error("Check your AWS credentials and ensure you're using the correct region.")
            else:
                logger.exception(f"AWS SES error ({error_code}): {error_message}")

            raise
        except Exception as e:
            logger.exception(f"Error sending email: {e!s}")
            raise

    async def send_reply(
        self,
        original_email: dict[str, Any],
        reply_text: str,
        reply_html: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Send a reply to an original email, making it appear as a reply in email clients.

        Args:
            original_email: The original email data
            reply_text: The plain text reply body
            reply_html: The HTML reply body (optional)

        Returns:
            The response from AWS SES

        """
        try:
            # Extract necessary information from the original email
            to_address = original_email.get("from")  # Reply to the sender
            original_subject = original_email.get("subject", "")

            # Use the "to" address from the original email as the sender
            # This makes the reply appear to come from the same address that received the original email
            sender_email = original_email.get("to", self.default_sender_email)

            # Create a reply subject with "Re:" prefix if not already present
            subject = original_subject
            if not subject.lower().startswith("re:"):
                subject = f"Re: {subject}"

            # Get message ID and references for threading
            message_id = original_email.get("messageId")
            references = original_email.get("references", "")

            # Prepare headers for email threading
            headers = {}

            # Add In-Reply-To and References headers if message ID is available
            if message_id:
                # Make sure message ID is properly formatted with angle brackets
                if not message_id.startswith("<"):
                    message_id = f"<{message_id}>"
                if not message_id.endswith(">"):
                    message_id = f"{message_id}>"

                headers["InReplyTo"] = {"Data": message_id}

                # Add the message ID to references
                if references:
                    # Make sure references are properly formatted
                    if not references.startswith("<"):
                        references = f"<{references}>"
                    if not references.endswith(">"):
                        references = f"{references}>"
                    headers["References"] = {"Data": f"{references} {message_id}"}
                else:
                    headers["References"] = {"Data": message_id}

            # Create email parameters
            message = {
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": reply_text}}
            }

            if reply_html:
                message["Body"]["Html"] = {"Data": reply_html}

            email_params = {
                "Source": sender_email,
                "Destination": {"ToAddresses": [to_address]},
                "Message": message
            }

            # Add headers to the message if present
            # if headers:
            #     for name, value in headers.items():
            #         # This is incorrect
            #         if name == "InReplyTo":
            #             email_params["ReplyToAddresses"] = [value["Data"]]
            #         elif name == "References":
            #             # References can't be added directly in SES, we'll skip it
            #             continue

            # Add CC if present in original email
            cc_addresses = []
            if original_email.get("cc"):
                cc_addresses.append(original_email["cc"])
            if cc_addresses:
                email_params["Destination"]["CcAddresses"] = cc_addresses

            # Send the email
            logger.info(f"Sending reply from {sender_email} to {to_address} with subject: {subject}")
            response = self.ses_client.send_email(**email_params)
            logger.info(f"Reply sent successfully: {response['MessageId']}")
            return response

        except Exception as e:
            logger.exception(f"Error sending reply: {e!s}")
            raise

async def verify_sender_email(email_address: str) -> bool:
    """
    Verify a sender email address with AWS SES.
    """
    try:
        # AWS SES client configuration
        region = os.getenv("AWS_REGION", "us-east-1")
        access_key = os.getenv("AWS_ACCESS_KEY_ID")
        secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        session_token = os.getenv("AWS_SESSION_TOKEN")

        # Initialize SES client
        ses_client = boto3.client(
            "ses",
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            **({"aws_session_token": session_token} if session_token else {})
        )

        # Request email verification
        ses_client.verify_email_identity(EmailAddress=email_address)
        logger.info(f"Verification email sent to {email_address}")
        return True

    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        logger.error(f"Failed to verify email ({error_code}): {error_message}")
        return False

    except Exception as e:
        logger.exception(f"Error during email verification: {e!s}")
        return False

async def test_send_email(to_address, subject="Test from mxtoai", body_text="This is a test email"):
    """
    Test email sending functionality.
    """
    try:
        sender = EmailSender()
        response = await sender.send_email(
            to_address=to_address,
            subject=subject,
            body_text=body_text
        )
        logger.info(f"Test email sent successfully: {response['MessageId']}")
        return True
    except Exception as e:
        logger.exception(f"Failed to send test email: {e!s}")
        return False

async def run_tests():
    """
    Run a series of tests for email functionality.
    """
    test_email = os.getenv("TEST_EMAIL")
    if not test_email:
        logger.error("TEST_EMAIL environment variable not set")
        return False

    tests = [
        ("Basic Send", lambda: test_send_email(test_email)),
        ("Verify Email", lambda: verify_sender_email(test_email))
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
            logger.info(f"Test '{test_name}' {'passed' if result else 'failed'}")
        except Exception as e:
            results.append((test_name, False))
            logger.exception(f"Test '{test_name}' failed with error: {e!s}")

    return all(result for _, result in results)

def log_received_email(email_data: EmailRequest) -> None:
    """
    Log details about a received email.
    """
    logger.info(f"Received email from {email_data.from_email} to {email_data.to}")
    logger.info(f"Subject: {email_data.subject}")
    logger.info(f"Text Content: {email_data.textContent}")
    logger.info(f"HTML Content: {email_data.htmlContent}")
    logger.info(f"Number of attachments: {len(email_data.attachments) if email_data.attachments else 0}")

def generate_email_id(email_data: EmailRequest) -> str:
    """
    Generate a unique ID for an email based on its metadata.
    """
    timestamp = int(time.time())
    hash_input = f"{email_data.from_email}-{email_data.to}-{timestamp}"
    return f"{timestamp}--{abs(hash(hash_input))}"

def save_attachments(email_data: EmailRequest, email_id: str) -> tuple[str, list[dict[str, Any]]]:
    """
    Save email attachments to disk and return their metadata.
    """
    if not email_data.attachments:
        return ATTACHMENTS_DIR, []

    # Create directory for this email's attachments
    email_dir = os.path.join(ATTACHMENTS_DIR, email_id)
    os.makedirs(email_dir, exist_ok=True)

    attachment_info = []
    for attachment in email_data.attachments:
        try:
            # Generate a safe filename
            filename = attachment.filename
            file_path = os.path.join(email_dir, filename)

            # Save the file
            with open(file_path, "wb") as f:
                f.write(base64.b64decode(attachment.content))

            # Get file metadata
            file_size = os.path.getsize(file_path)
            attachment_info.append({
                "filename": filename,
                "path": file_path,
                "size": file_size,
                "type": attachment.contentType
            })

            logger.info(f"Saved attachment: {filename} ({file_size} bytes)")

        except Exception as e:
            logger.exception(f"Error saving attachment {attachment.filename}: {e!s}")
            # Continue with other attachments even if one fails
            continue

    return email_dir, attachment_info

def prepare_email_for_ai(email_data: EmailRequest, attachment_info: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Prepare email data for AI processing.
    """
    # Create a copy to avoid modifying the original
    email_dict = deepcopy(email_data.dict())

    # Add attachment information
    email_dict["attachments"] = attachment_info

    # Convert any binary data to base64
    if "textContent" in email_dict and isinstance(email_dict["textContent"], bytes):
        email_dict["textContent"] = base64.b64encode(email_dict["textContent"]).decode()

    if "htmlContent" in email_dict and isinstance(email_dict["htmlContent"], bytes):
        email_dict["htmlContent"] = base64.b64encode(email_dict["htmlContent"]).decode()

    return email_dict

async def generate_email_summary(email_dict: dict[str, Any], attachment_info: list[dict[str, Any]]) -> str:
    """
    Generate a summary of the email and its attachments using AI.
    """
    # TODO: Implement AI-based summarization
    return f"Email from {email_dict['from_email']} with {len(attachment_info)} attachments"

def create_reply_content(summary: str, attachment_info: list[dict[str, Any]]) -> tuple[str, str]:
    """
    Create the content for the email reply in both text and HTML formats.
    """
    # Create plain text version
    text_content = [
        "Thank you for your email. Here's what I found:",
        "",
        summary,
        "",
        "Attachments processed:",
    ]

    for attachment in attachment_info:
        text_content.append(f"- {attachment['filename']} ({attachment['size']} bytes)")

    text_content.extend([
        "",
        "Best regards,",
        "AI Assistant"
    ])

    # Create HTML version
    html_content = [
        "<html><body>",
        "<p>Thank you for your email. Here's what I found:</p>",
        f"<p>{summary}</p>",
        "<h3>Attachments processed:</h3>",
        "<ul>"
    ]

    for attachment in attachment_info:
        html_content.append(
            f"<li>{attachment['filename']} ({attachment['size']} bytes)</li>"
        )

    html_content.extend([
        "</ul>",
        "<p>Best regards,<br>AI Assistant</p>",
        "</body></html>"
    ])

    return "\n".join(text_content), "\n".join(html_content)

async def send_email_reply(email_dict: dict[str, Any], reply_text: str, reply_html: str) -> dict[str, Any]:
    """
    Send a reply to the original email.
    """
    try:
        sender = EmailSender()
        return await sender.send_reply(
            original_email=email_dict,
            reply_text=reply_text,
            reply_html=reply_html
        )
    except Exception as e:
        logger.exception(f"Error sending reply: {e!s}")
        raise
