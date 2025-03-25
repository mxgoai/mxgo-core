import boto3
import os
from typing import Dict, List, Optional, Any
import logging
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# Load environment variables
load_dotenv()

# Initialize logger
logger = logging.getLogger("mxtoai.email")
logger.setLevel(logging.INFO)

class EmailSender:
    """
    Class to handle sending emails via AWS SES, including replies to original emails.
    """

    def __init__(self):
        """
        Initialize the AWS SES client.
        """
        # AWS SES client configuration
        region = os.getenv('AWS_REGION', 'us-east-1')
        access_key = os.getenv('AWS_ACCESS_KEY_ID')
        secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        session_token = os.getenv('AWS_SESSION_TOKEN')

        # Validate required credentials
        if not access_key or not secret_key:
            logger.error("AWS credentials missing: Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            raise ValueError("AWS credentials missing")

        # Build SES config
        ses_config = {
            'region_name': region
        }

        # Try different ways to initialize the client until one works
        self.ses_client = None
        errors = []

        # Method 1: Use explicit credentials
        try:
            logger.info(f"Attempting to initialize SES client with explicit credentials in region {region}")
            self.ses_client = boto3.client(
                'ses',
                region_name=region,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                **({"aws_session_token": session_token} if session_token else {})
            )
            # Test connection
            self.ses_client.get_send_quota()
            logger.info("SES client initialized successfully with explicit credentials")
        except Exception as e:
            errors.append(f"Method 1 failed: {str(e)}")
            self.ses_client = None

        # # Method 2: Use boto3 default credentials chain
        # if not self.ses_client:
        #     try:
        #         logger.info("Attempting to initialize SES client with default credential chain")
        #         self.ses_client = boto3.client('ses', region_name=region)
        #         # Test connection
        #         self.ses_client.get_send_quota()
        #         logger.info("SES client initialized successfully with default credential chain")
        #     except Exception as e:
        #         errors.append(f"Method 2 failed: {str(e)}")
        #         self.ses_client = None

        # # If still not connected, try with a session
        # if not self.ses_client:
        #     try:
        #         logger.info("Attempting to initialize SES client with a boto3 session")
        #         session = boto3.Session(
        #             aws_access_key_id=access_key,
        #             aws_secret_access_key=secret_key,
        #             aws_session_token=session_token,
        #             region_name=region
        #         )
        #         self.ses_client = session.client('ses')
        #         # Test connection
        #         self.ses_client.get_send_quota()
        #         logger.info("SES client initialized successfully with a boto3 session")
        #     except Exception as e:
        #         errors.append(f"Method 3 failed: {str(e)}")
        #         self.ses_client = None

        # If all methods failed, raise an exception with details
        if not self.ses_client:
            error_details = "\n".join(errors)
            logger.error(f"Failed to initialize SES client after all attempts:\n{error_details}")
            raise ConnectionError(f"Could not connect to AWS SES: {error_details}")

        self.default_sender_email = os.getenv('SENDER_EMAIL', 'ai-assistant@mxtoai.com')
        logger.info(f"EmailSender initialized with default sender: {self.default_sender_email}")

    async def send_email(
        self,
        to_address: str,
        subject: str,
        body_text: str,
        body_html: Optional[str] = None,
        cc_addresses: Optional[List[str]] = None,
        reply_to_addresses: Optional[List[str]] = None,
        sender_email: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Send an email using AWS SES.
        """
        try:
            # Use provided sender_email or fall back to default
            source_email = sender_email or self.default_sender_email

            message = {
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': body_text}}
            }

            if body_html:
                message['Body']['Html'] = {'Data': body_html}

            email_params = {
                'Source': source_email,
                'Destination': {'ToAddresses': [to_address]},
                'Message': message
            }

            if cc_addresses:
                email_params['Destination']['CcAddresses'] = cc_addresses

            if reply_to_addresses:
                email_params['ReplyToAddresses'] = reply_to_addresses

            logger.info(f"Sending email from {source_email} to {to_address} with subject: {subject}")
            response = self.ses_client.send_email(**email_params)
            logger.info(f"Email sent successfully: {response['MessageId']}")
            return response

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))

            if error_code == 'MessageRejected':
                logger.error(f"Email rejected: {error_message}")
                if "Email address is not verified" in error_message:
                    logger.error(f"The sender email '{source_email}' is not verified in SES. "
                                f"Verify it in the AWS SES console or use a different verified email.")
            elif error_code == 'SignatureDoesNotMatch':
                logger.error(f"AWS authentication failed: {error_message}")
                logger.error("Check your AWS credentials and ensure you're using the correct region.")
            else:
                logger.exception(f"AWS SES error ({error_code}): {error_message}")

            raise
        except Exception as e:
            logger.exception(f"Error sending email: {str(e)}")
            raise

    async def send_reply(
        self,
        original_email: Dict[str, Any],
        reply_text: str,
        reply_html: Optional[str] = None
    ) -> Dict[str, Any]:
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
            to_address = original_email.get('from')  # Reply to the sender
            original_subject = original_email.get('subject', '')

            # Use the "to" address from the original email as the sender
            # This makes the reply appear to come from the same address that received the original email
            sender_email = original_email.get('to', self.default_sender_email)

            # Create a reply subject with "Re:" prefix if not already present
            subject = original_subject
            if not subject.lower().startswith('re:'):
                subject = f"Re: {subject}"

            # Get message ID and references for threading
            message_id = original_email.get('messageId')
            references = original_email.get('references', '')

            # Prepare headers for email threading
            headers = {}

            # Add In-Reply-To and References headers if message ID is available
            if message_id:
                # Make sure message ID is properly formatted with angle brackets
                if not message_id.startswith('<'):
                    message_id = f"<{message_id}>"
                if not message_id.endswith('>'):
                    message_id = f"{message_id}>"

                headers['InReplyTo'] = {'Data': message_id}

                # Add the message ID to references
                if references:
                    # Make sure references are properly formatted
                    if not references.startswith('<'):
                        references = f"<{references}>"
                    if not references.endswith('>'):
                        references = f"{references}>"
                    headers['References'] = {'Data': f"{references} {message_id}"}
                else:
                    headers['References'] = {'Data': message_id}

            # Create email parameters
            message = {
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': reply_text}}
            }

            if reply_html:
                message['Body']['Html'] = {'Data': reply_html}

            email_params = {
                'Source': sender_email,
                'Destination': {'ToAddresses': [to_address]},
                'Message': message
            }

            # Add CC if present in original email
            cc_addresses = []
            if original_email.get('cc'):
                cc_addresses.append(original_email['cc'])
            if cc_addresses:
                email_params['Destination']['CcAddresses'] = cc_addresses

            # Add threading information through other parameters if needed
            if message_id:
                # Use ReplyToAddresses which is supported by the SES API
                email_params['ReplyToAddresses'] = [sender_email]

            logger.info(f"Sending reply from {sender_email} to {to_address} with subject: {subject}")
            response = self.ses_client.send_email(**email_params)
            logger.info(f"Reply sent successfully: {response['MessageId']}")
            return response

        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))

            if error_code == 'MessageRejected':
                logger.error(f"Reply email rejected: {error_message}")
                if "Email address is not verified" in error_message:
                    logger.error(f"The sender email '{sender_email}' is not verified in SES. "
                                f"Verify it in the AWS SES console or use a different verified email.")
            elif error_code == 'SignatureDoesNotMatch':
                logger.error(f"AWS authentication failed: {error_message}")
                logger.error("Check your AWS credentials and ensure you're using the correct region.")
            else:
                logger.exception(f"AWS SES error ({error_code}): {error_message}")

            raise
        except Exception as e:
            logger.exception(f"Error sending reply: {str(e)}")
            raise

# Create and export an instance of EmailSender
email_sender = EmailSender()


# Quick verification function for sender emails
async def verify_sender_email(email_address: str) -> bool:
    """
    Verify an email address with SES so it can be used as a sender.
    """
    try:
        # First check if email is already verified
        try:
            identities = email_sender.ses_client.list_identities(
                IdentityType='EmailAddress'
            )
            verified_emails = identities.get('Identities', [])

            if email_address in verified_emails:
                logger.info(f"Email '{email_address}' is already verified in SES")
                return True
        except Exception as e:
            logger.warning(f"Could not check if {email_address} is already verified: {str(e)}")

        # Attempt to send verification email
        response = email_sender.ses_client.verify_email_identity(
            EmailAddress=email_address
        )
        logger.info(f"Verification email sent to '{email_address}'")
        return True
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_message = e.response.get('Error', {}).get('Message', str(e))

        if error_code == 'SignatureDoesNotMatch':
            logger.error(f"AWS authentication failed during email verification: {error_message}")
            logger.error("Check your AWS credentials and ensure you're using the correct region.")
        elif error_code == 'InvalidParameterValue':
            logger.error(f"Invalid email address format: {email_address}")
        else:
            logger.exception(f"AWS SES error during verification ({error_code}): {error_message}")

        return False
    except Exception as e:
        logger.exception(f"Error verifying email address: {str(e)}")
        return False



async def test_send_email(to_address, subject="Test from mxtoai", body_text="This is a test email"):
    """Send a test email."""
    try:
        result = await email_sender.send_email(
            to_address=to_address,
            subject=subject,
            body_text=body_text,
            body_html=f"<html><body><h1>{subject}</h1><p>{body_text}</p></body></html>"
        )
        logger.info(f"Test email sent to {to_address}, message ID: {result.get('MessageId', 'unknown')}")
        return True
    except Exception as e:
        logger.error(f"Failed to send test email: {str(e)}")
        return False


if __name__ == "__main__":
    import asyncio

    # Configuration values - change these as needed
    RECIPIENT_EMAIL = "satwikkansal@gmail.com"  # Change to a valid recipient
    TEST_SENDER = None  # Set to a specific sender or None to use default

    async def run_tests():
        """Run the email tests."""
        logger.info("=== AWS SES Email Testing ===")
        logger.info(f"Region: {os.getenv('AWS_REGION', 'Not set')}")
        logger.info(f"Default sender: {email_sender.default_sender_email}")

        # Test SES connection
        if not await test_connection():
            logger.error("Connection test failed. Cannot proceed with email tests.")
            return

        # Send test email if recipient is specified
        if RECIPIENT_EMAIL and RECIPIENT_EMAIL != "your-email@example.com":
            logger.info(f"Sending test email to {RECIPIENT_EMAIL}")
            await test_send_email(
                to_address=RECIPIENT_EMAIL,
                subject="Test Email from mxtoai",
                body_text="This is a test email from the mxtoai email assistant."
            )
        else:
            logger.info("Skipping test email - please set a valid RECIPIENT_EMAIL")

    # Run the tests
    asyncio.run(run_tests())
