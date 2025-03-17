import boto3
import os
from typing import Dict, List, Optional, Any
from _logging import get_logger
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger("email")

class EmailSender:
    """
    Class to handle sending emails via AWS SES, including replies to original emails.
    """
    
    def __init__(self):
        """
        Initialize the AWS SES client.
        """
        self.ses_client = boto3.client(
            'ses',
            region_name=os.getenv('AWS_REGION', 'us-east-1'),
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY')
        )
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
        
        Args:
            to_address: The recipient's email address
            subject: The email subject
            body_text: The plain text email body
            body_html: The HTML email body (optional)
            cc_addresses: List of CC addresses (optional)
            reply_to_addresses: List of Reply-To addresses (optional)
            sender_email: The sender's email address (optional, defaults to self.default_sender_email)
            
        Returns:
            The response from AWS SES
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
            
        except Exception as e:
            logger.error(f"Error sending email: {str(e)}")
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
            
            # Add headers for email threading
            if headers:
                email_params['Headers'] = [
                    {'Name': name, 'Value': value['Data']} 
                    for name, value in headers.items()
                ]
            
            logger.info(f"Sending reply from {sender_email} to {to_address} with subject: {subject}")
            response = self.ses_client.send_email(**email_params)
            logger.info(f"Reply sent successfully: {response['MessageId']}")
            return response
            
        except Exception as e:
            logger.error(f"Error sending reply: {str(e)}")
            raise

# Create a singleton instance
email_sender = EmailSender() 