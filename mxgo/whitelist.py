import os
import uuid
from datetime import datetime, timezone

from supabase import Client, create_client

from mxgo._logging import get_logger
from mxgo.email_sender import EmailSender

logger = get_logger(__name__)

# Initialize Supabase client
supabase: Client | None = None


def is_whitelist_enabled() -> bool:
    return os.getenv("WHITELIST_ENABLED", "false").strip().lower() == "true"


def init_supabase():
    """
    Initialize Supabase client
    """
    global supabase  # noqa: PLW0603
    if supabase is None:
        try:
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
            if not supabase_url or not supabase_key:
                msg = "Supabase URL and service role key must be set in environment variables"
                raise ValueError(msg)

            supabase = create_client(
                supabase_url=supabase_url,
                supabase_key=supabase_key,
            )
            logger.info("Supabase client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            raise


async def is_email_whitelisted(email: str) -> tuple[bool, bool]:
    """
    Check if an email is whitelisted and verified in the database

    Args:
        email: The email address to check

    Returns:
        Tuple[bool, bool]: (exists_in_whitelist, is_verified)

    """
    try:
        if not is_whitelist_enabled():
            logger.info(f"Whitelist feature is disabled. All emails treated as whitelisted: {email}")
            return True, True

        if not supabase:
            init_supabase()

        # Query the whitelist table for the email
        response = supabase.table("whitelisted_emails").select("*").eq("email", email).execute()

        # Check if email exists and is verified
        if hasattr(response, "data") and len(response.data) > 0:
            is_verified = response.data[0].get("verified", False)
            logger.info(f"Email whitelist check for {email}: exists=True, verified={is_verified}")
        else:
            logger.info(f"Email whitelist check for {email}: exists=False, verified=False")
            return False, False

    except Exception as e:
        logger.error(f"Error checking whitelist status for {email}: {e}")
        return False, False
    else:
        return True, is_verified


async def trigger_automatic_verification(email: str) -> bool:
    """
    Automatically trigger email verification for non-whitelisted users.

    This function:
    1. Generates a unique verification token
    2. Inserts/updates the email in whitelisted_emails table with verified=false
    3. Sends verification email using SES

    Args:
        email: The email address to verify

    Returns:
        bool: True if verification process was successfully triggered, False otherwise

    """
    try:
        if not supabase:
            init_supabase()

        # Generate unique verification token
        verification_token = str(uuid.uuid4())
        current_time = datetime.now(timezone.utc).isoformat()

        # Check if email already exists in whitelist
        existing_response = supabase.table("whitelisted_emails").select("*").eq("email", email).execute()

        if hasattr(existing_response, "data") and len(existing_response.data) > 0:
            # Email exists, update with new verification token
            update_response = (
                supabase.table("whitelisted_emails")
                .update({"verification_token": verification_token, "verified": False, "updated_at": current_time})
                .eq("email", email)
                .execute()
            )

            if hasattr(update_response, "data") and len(update_response.data) > 0:
                logger.info(f"Updated existing email {email} with new verification token")
            else:
                logger.error(f"Failed to update verification token for {email}")
                return False
        else:
            # Email doesn't exist, insert new record
            insert_response = (
                supabase.table("whitelisted_emails")
                .insert(
                    {
                        "email": email,
                        "verified": False,
                        "verification_token": verification_token,
                        "created_at": current_time,
                        "updated_at": current_time,
                    }
                )
                .execute()
            )

            if hasattr(insert_response, "data") and len(insert_response.data) > 0:
                logger.info(f"Inserted new email {email} with verification token")
            else:
                logger.error(f"Failed to insert verification record for {email}")
                return False

        # Send verification email
        verification_sent = await send_verification_email(email, verification_token)

        if verification_sent:
            logger.info(f"Successfully triggered automatic verification for {email}")
        else:
            logger.error(f"Failed to send verification email to {email}")

    except Exception as e:
        logger.error(f"Error triggering automatic verification for {email}: {e}")
        return False
    else:
        return verification_sent


async def send_verification_email(email: str, verification_token: str) -> bool:
    """
    Send verification email using SES email sender.

    Args:
        email: Recipient email address
        verification_token: Unique verification token

    Returns:
        bool: True if email was sent successfully, False otherwise

    """
    try:
        # Get the origin URL for verification links
        origin = os.getenv("FRONTEND_URL", "https://mxgo.ai")
        verification_url = f"{origin}/verify?token={verification_token}"

        # Create email content
        subject = "Verify your email for MXGo"

        text_content = f"""Welcome to MXGo!

To complete your registration and start using our email processing service, please verify your email address by clicking the link below:

{verification_url}

This verification link will expire in 24 hours for security reasons.

If you didn't request this verification, you can safely ignore this email.

Best regards,
MXGo Team

---
MXGo - Transform your emails with AI
https://mxgo.ai"""

        html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Verify your email - MXGo</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-align: center; padding: 30px 20px; border-radius: 8px 8px 0 0; }}
        .content {{ background: #ffffff; padding: 30px; border: 1px solid #e1e5e9; border-top: none; }}
        .button {{ display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; padding: 12px 30px; border-radius: 6px; font-weight: 600; margin: 20px 0; }}
        .footer {{ background: #f8f9fa; color: #6c757d; text-align: center; padding: 20px; border-radius: 0 0 8px 8px; font-size: 14px; }}
        .warning {{ background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; padding: 15px; border-radius: 6px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 style="margin: 0; font-size: 28px;">Welcome to MXGo!</h1>
        </div>
        <div class="content">
            <h2 style="color: #333; margin-top: 0;">Verify your email address</h2>
            <p>To complete your registration and start using our email processing service, please verify your email address by clicking the button below:</p>

            <div style="text-align: center; margin: 30px 0;">
                <a href="{verification_url}" class="button">Verify Email Address</a>
            </div>

            <p>Or copy and paste this link into your browser:</p>
            <p style="word-break: break-all; background: #f8f9fa; padding: 10px; border-radius: 4px; font-family: monospace;">{verification_url}</p>

            <div class="warning">
                <strong>⏰ Important:</strong> This verification link will expire in 24 hours for security reasons.
            </div>

            <p>If you didn't request this verification, you can safely ignore this email.</p>

            <p>Best regards,<br>
            <strong>MXGo Team</strong></p>
        </div>
        <div class="footer">
            <p><strong>MXGo</strong> - Transform your emails with AI</p>
            <p><a href="https://mxgo.ai" style="color: #667eea;">https://mxgo.ai</a></p>
        </div>
    </div>
</body>
</html>"""

        # Initialize email sender and send verification email
        email_sender = EmailSender()
        response = await email_sender.send_email(
            to_address=email, subject=subject, body_text=text_content, body_html=html_content
        )

        logger.info(f"Verification email sent successfully to {email}: {response.get('MessageId', 'Unknown')}")
        return True

    except Exception as e:
        logger.error(f"Error sending verification email to {email}: {e}")
        return False
    else:
        return True


def get_whitelist_signup_url() -> str:
    """
    Get the URL where users can sign up to be whitelisted

    Returns:
        str: The URL for whitelist signup

    """
    return os.getenv("WHITELIST_SIGNUP_URL", "https://mxgo.ai/whitelist")
