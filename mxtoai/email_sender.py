import base64
import os
import time
from copy import deepcopy
from pathlib import Path
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

# Add imports for MIME handling
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


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
                **({"aws_session_token": session_token} if session_token else {}),
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
        sender_email: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Send an email using AWS SES.
        """
        try:
            # Use provided sender_email or fall back to default
            source_email = sender_email or self.default_sender_email

            message = {"Subject": {"Data": subject}, "Body": {"Text": {"Data": body_text}}}

            if body_html:
                message["Body"]["Html"] = {"Data": body_html}

            email_params = {"Source": source_email, "Destination": {"ToAddresses": [to_address]}, "Message": message}

            if cc_addresses:
                email_params["Destination"]["CcAddresses"] = cc_addresses

            if reply_to_addresses:
                email_params["ReplyToAddresses"] = reply_to_addresses

            logger.info(f"Sending email from {source_email} to {to_address} with subject: {subject}")
            response = self.ses_client.send_email(**email_params)

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))

            if error_code == "MessageRejected":
                logger.error(f"Email rejected: {error_message}")
                if "Email address is not verified" in error_message:
                    logger.error(
                        f"The sender email '{source_email}' is not verified in SES. "
                        f"Verify it in the AWS SES console or use a different verified email."
                    )
            elif error_code == "SignatureDoesNotMatch":
                logger.error(f"AWS authentication failed: {error_message}")
                logger.error("Check your AWS credentials and ensure you're using the correct region.")
            else:
                logger.exception(f"AWS SES error ({error_code}): {error_message}")

            raise
        except Exception:
            logger.exception("Error sending email")
            raise
        else:
            logger.info(f"Email sent successfully: {response['MessageId']}")
            return response

    def _create_mime_message(
        self, original_email: dict[str, Any], subject: str, sender_email: str, to_address: str
    ) -> MIMEMultipart:
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = sender_email
        msg["To"] = to_address

        cc_addresses = []
        original_cc_data = original_email.get("cc")
        if original_cc_data:
            if isinstance(original_cc_data, str):
                potential_ccs = [addr.strip() for addr in original_cc_data.split(",") if addr.strip()]
                cc_addresses = [addr for addr in potential_ccs if isinstance(addr, str) and "@" in addr]
                if len(cc_addresses) != len(potential_ccs):
                    logger.warning(f"Filtered invalid CC addresses from string: {original_cc_data}")
            elif isinstance(original_cc_data, list):
                cc_addresses = [addr for addr in original_cc_data if isinstance(addr, str) and "@" in addr]
                if len(cc_addresses) != len(original_cc_data):
                    logger.warning(f"Filtered invalid CC addresses from list: {original_cc_data}")
            else:
                logger.warning(f"CC field was not a string or list: {original_cc_data}")

        if cc_addresses:
            msg["Cc"] = ", ".join(cc_addresses)
            logger.info(f"Adding valid CC addresses to reply: {cc_addresses}")

        message_id = original_email.get("messageId")
        references = original_email.get("references", "")
        if message_id:
            if not message_id.startswith("<"):
                message_id = f"<{message_id}"
            if not message_id.endswith(">"):
                message_id = f"{message_id}>"
            msg["In-Reply-To"] = message_id
            msg["References"] = f"{references} {message_id}".strip() if references else message_id
        return msg

    def _create_alternative_body_part(self, reply_text: str, reply_html: Optional[str] = None) -> MIMEMultipart:
        msg_alternative = MIMEMultipart("alternative")
        msg_text = MIMEText(reply_text, "plain", "utf-8")
        msg_alternative.attach(msg_text)
        if reply_html:
            msg_html = MIMEText(reply_html, "html", "utf-8")
            msg_alternative.attach(msg_html)
        return msg_alternative

    def _attach_files_to_message(self, msg: MIMEMultipart, attachments: Optional[list[dict[str, Any]]] = None):
        if not attachments:
            return

        for attachment in attachments:
            try:
                filename = attachment["filename"]
                content = attachment["content"]
                mimetype = attachment["mimetype"]
                maintype, subtype = mimetype.split("/", 1)

                attachment_content_bytes = content.encode("utf-8") if isinstance(content, str) else content
                part = MIMEApplication(attachment_content_bytes, Name=filename)
                part.add_header("Content-Disposition", "attachment", filename=filename)

                if maintype == "text" and subtype == "calendar":
                    part.replace_header("Content-Type", "text/calendar; method=PUBLISH; charset=utf-8")
                    logger.info(f"Setting Content-Type for {filename} to text/calendar; method=PUBLISH")
                else:
                    part.replace_header("Content-Type", mimetype)
                    logger.info(f"Setting Content-Type for {filename} to {mimetype}")

                msg.attach(part)
                logger.info(f"Attached file using MIMEApplication: {filename} ({mimetype})")
            except KeyError as ke:
                logger.error(f"Skipping attachment {attachment.get('filename', '(unknown)')} due to missing key: {ke}")
            except Exception as attach_err:
                logger.error(f"Error attaching file '{attachment.get('filename', '(unknown)')}': {attach_err}")

    async def send_reply(
        self,
        original_email: dict[str, Any],
        reply_text: str,
        reply_html: Optional[str] = None,
        attachments: Optional[list[dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        logger.info(f"Processing reply with attachments: {bool(attachments)}")
        try:
            to_address = original_email.get("from")
            if not to_address:
                msg_val_err = "Original email 'from' address is missing for reply"
                logger.error(msg_val_err)
                raise ValueError(msg_val_err)

            original_subject = original_email.get("subject", "")
            sender_email = original_email.get("to", self.default_sender_email)
            if not sender_email:
                msg_val_err = "Original recipient ('to' field) missing in email data for reply."
                logger.error(msg_val_err)
                raise ValueError(msg_val_err)

            subject = f"Re: {original_subject}" if not original_subject.lower().startswith("re:") else original_subject

            msg = self._create_mime_message(original_email, subject, sender_email, to_address)

            msg_alternative = self._create_alternative_body_part(reply_text, reply_html)
            msg.attach(msg_alternative)

            self._attach_files_to_message(msg, attachments)

            destinations = [to_address]
            # Retrieve cc_addresses from the created msg object if needed for Destinations
            # This assumes _create_mime_message correctly sets the 'Cc' header.
            if msg["Cc"]:
                # Note: msg["Cc"] will be a string. boto3 needs a list for Destinations.
                # email.utils.getaddresses can parse this, but we already validated them.
                # Simplest is to re-retrieve the validated list if it was stored, or parse msg["Cc"]
                # For now, let's assume the original cc_addresses list might be accessible or re-derived if needed.
                # However, the Destinations field in send_raw_email takes all recipients (To, Cc, Bcc).
                # Boto3 SES send_raw_email Destinations are implicitly handled by To, Cc, Bcc fields in MIME message for SES.
                # So, explicit cc_addresses in Destinations list for send_raw_email is usually not needed if Cc header is set.
                # For clarity, let's get them if they were set.
                parsed_cc_addresses = [addr.strip() for addr in msg["Cc"].split(",") if addr.strip()]
                destinations.extend(parsed_cc_addresses)

            logger.info(
                f"Sending raw reply from {sender_email} to {to_address} (CC: {msg.get('Cc', 'None')}) with subject: {msg['Subject']}"
            )
            response = self.ses_client.send_raw_email(
                Source=sender_email, Destinations=destinations, RawMessage={"Data": msg.as_string()}
            )

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            error_message = e.response.get("Error", {}).get("Message", str(e))
            # Log the sender email being used when verification fails
            if error_code == "MessageRejected":
                logger.error(f"Email rejected: {error_message}")
                if "Email address is not verified" in error_message:
                    logger.error(
                        f"The sender email '{sender_email}' is not verified in SES. "
                        f"Verify it in the AWS SES console or use a different verified email."
                    )
            elif error_code == "SignatureDoesNotMatch":
                logger.error(f"AWS authentication failed: {error_message}")
                logger.error("Check your AWS credentials and ensure you're using the correct region.")
            else:
                logger.exception(f"AWS SES error sending raw email ({error_code}): {error_message}")

            raise  # Re-raise the exception after logging
        except Exception:
            logger.exception("Error sending raw reply")
            raise
        else:
            logger.info(f"Raw reply sent successfully: {response['MessageId']}")
            return response


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
            **({"aws_session_token": session_token} if session_token else {}),
        )

        # Verify email identity
        ses_client.verify_email_identity(EmailAddress=email_address)
        logger.info(f"Verification email sent to {email_address}")
    except ClientError as e:
        logger.error(f"AWS SES ClientError during email verification for {email_address}: {e!s}")
        return False
    except Exception:
        logger.exception("Error during email verification")
        return False
    else:
        return True


async def test_send_email(to_address, subject="Test from mxtoai", body_text="This is a test email"):
    """
    Test email sending functionality.
    """
    try:
        sender = EmailSender()
        response = await sender.send_email(to_address=to_address, subject=subject, body_text=body_text)
    except Exception:
        logger.exception("Failed to send test email")
        return False
    else:
        logger.info(f"Test email sent successfully: {response['MessageId']}")
        return True


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
        ("Verify Email", lambda: verify_sender_email(test_email)),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
            logger.info(f"Test '{test_name}' {'passed' if result else 'failed'}")
        except Exception:
            results.append((test_name, False))
            logger.exception(f"Test '{test_name}' failed with error")

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
    email_dir = Path(ATTACHMENTS_DIR) / email_id
    email_dir.mkdir(parents=True, exist_ok=True)

    attachment_info = []
    for attachment in email_data.attachments:
        try:
            # Generate a safe filename
            filename = Path(attachment.filename).name  # Ensure filename is just the name part
            file_path = email_dir / filename

            # Save the file
            with file_path.open("wb") as f:
                f.write(base64.b64decode(attachment.content))

            # Get file metadata
            file_size = file_path.stat().st_size
            attachment_info.append(
                {"filename": filename, "path": str(file_path), "size": file_size, "type": attachment.contentType}
            )

            logger.info(f"Saved attachment: {filename} ({file_size} bytes)")

        except Exception:
            logger.exception(f"Error saving attachment {attachment.filename}")
            # Continue with other attachments even if one fails
            continue

    return str(email_dir), attachment_info


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

    text_content.extend([f"- {attachment['filename']} ({attachment['size']} bytes)" for attachment in attachment_info])

    text_content.extend(["", "Best regards,", "AI Assistant"])

    # Create HTML version
    html_content = [
        "<html><body>",
        "<p>Thank you for your email. Here's what I found:</p>",
        f"<p>{summary}</p>",
        "<h3>Attachments processed:</h3>",
        "<ul>",
    ]

    html_content.extend(
        [f"<li>{attachment['filename']} ({attachment['size']} bytes)</li>" for attachment in attachment_info]
    )

    html_content.extend(["</ul>", "<p>Best regards,<br>AI Assistant</p>", "</body></html>"])

    return "\n".join(text_content), "".join(html_content)


async def send_email_reply(email_dict: dict[str, Any], reply_text: str, reply_html: str) -> dict[str, Any]:
    """
    Send a reply to the original email.
    """
    sender = EmailSender()
    try:
        return await sender.send_reply(original_email=email_dict, reply_text=reply_text, reply_html=reply_html)
    except Exception:
        logger.exception("Error sending reply")
        raise
