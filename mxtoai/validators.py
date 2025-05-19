import json
import os
from typing import Optional

from fastapi import Response, status

from mxtoai._logging import get_logger
from mxtoai.email_sender import send_email_reply
from mxtoai.handle_configuration import HANDLE_MAP
from mxtoai.whitelist import get_whitelist_signup_url, is_email_whitelisted

logger = get_logger(__name__)


async def validate_api_key(api_key: str) -> Optional[Response]:
    """
    Validate the API key.

    Args:
        api_key: The API key to validate

    Returns:
        Response if validation fails, None if validation succeeds

    """
    if api_key != os.environ["X_API_KEY"]:
        return Response(
            content=json.dumps({"message": "Invalid API key", "status": "error"}),
            status_code=status.HTTP_401_UNAUTHORIZED,
            media_type="application/json",
        )
    return None


async def validate_email_whitelist(
    from_email: str, to: str, subject: str, messageId: Optional[str]
) -> Optional[Response]:
    """
    Validate if the sender's email is whitelisted and verified.

    Args:
        from_email: Sender's email address
        to: Recipient's email address
        subject: Email subject
        messageId: Email message ID

    Returns:
        Response if validation fails, None if validation succeeds

    """
    exists_in_whitelist, is_verified = await is_email_whitelisted(from_email)

    if not exists_in_whitelist:
        # Case 1: Email not in whitelist at all
        signup_url = get_whitelist_signup_url()
        rejection_msg = f"""Your email address is not whitelisted in our system.

To use our email processing service, please visit {signup_url} to request access.

Once your email is added to the whitelist and verified, you can resend your email for processing.

Best,
MX to AI Team"""

        html_rejection = f"""<p>Your email address is not whitelisted in our system.</p>
<p>To use our email processing service, please visit <a href="{signup_url}">{signup_url}</a> to request access.</p>
<p>Once your email is added to the whitelist and verified, you can resend your email for processing.</p>
<p>Best regards,<br>MX to AI Team</p>"""

    elif not is_verified:
        # Case 2: Email in whitelist but not verified
        signup_url = get_whitelist_signup_url()
        rejection_msg = f"""Your email is registered but not yet verified.

Please check your email for a verification link we sent when you registered. If you can't find it, you can request a new verification link at {signup_url}.

Once verified, you can resend your email for processing.

Best,
MX to AI Team"""

        html_rejection = f"""<p>Your email is registered but not yet verified.</p>
<p>Please check your email for a verification link we sent when you registered. If you can't find it, you can request a new verification link at <a href="{signup_url}">{signup_url}</a>.</p>
<p>Once verified, you can resend your email for processing.</p>
<p>Best regards,<br>MX to AI Team</p>"""
    else:
        # Email exists and is verified
        return None

    # Send rejection email for both unverified and non-existent cases
    email_dict = {
        "from": from_email,  # Original sender becomes recipient
        "to": to,  # Original recipient becomes sender
        "subject": f"Re: {subject}",
        "messageId": messageId,
        "references": None,
        "inReplyTo": messageId,
        "cc": None,
    }

    try:
        await send_email_reply(email_dict, rejection_msg, html_rejection)
        logger.info(
            f"Sent whitelist rejection email to {from_email} (exists={exists_in_whitelist}, verified={is_verified})"
        )
    except Exception as e:
        logger.error(f"Failed to send whitelist rejection email: {e}")

    # Return appropriate error response
    status_message = "Email not whitelisted" if not exists_in_whitelist else "Email not verified"
    return Response(
        content=json.dumps(
            {
                "message": f"Email rejected - {status_message}",
                "email": from_email,
                "exists_in_whitelist": exists_in_whitelist,
                "is_verified": is_verified,
                "rejection_sent": True,
            }
        ),
        status_code=status.HTTP_403_FORBIDDEN,
        media_type="application/json",
    )


async def validate_email_handle(
    to: str, from_email: str, subject: str, messageId: Optional[str]
) -> tuple[Optional[Response], Optional[str]]:
    """
    Validate if the email handle/alias is supported.

    Args:
        to: Recipient's email address
        from_email: Sender's email address
        subject: Email subject
        messageId: Email message ID

    Returns:
        Tuple of (Response if validation fails, handle if validation succeeds)

    """
    handle = to.split("@")[0].lower()
    email_instructions = HANDLE_MAP.get(handle)

    if not email_instructions:
        rejection_msg = "This email alias is not supported. Please visit https://mxtoai.com/docs/email-handles to learn about supported email handles."

        # Create email dict with proper format
        email_dict = {
            "from": from_email,  # Original sender becomes recipient
            "to": to,  # Original recipient becomes sender
            "subject": f"Re: {subject}",
            "messageId": messageId,
            "references": None,
            "inReplyTo": messageId,
            "cc": None,
        }

        try:
            await send_email_reply(email_dict, rejection_msg, rejection_msg)
            logger.info(f"Sent handle rejection email to {from_email}")
        except Exception as e:
            logger.error(f"Failed to send handle rejection email: {e}")

        return Response(
            content=json.dumps({"message": "Unsupported email handle", "handle": handle, "rejection_sent": True}),
            status_code=status.HTTP_400_BAD_REQUEST,
            media_type="application/json",
        ), None

    return None, handle


async def validate_attachments(
    attachments: list[dict], from_email: str, to: str, subject: str, messageId: Optional[str]
) -> Optional[Response]:
    """
    Validate email attachments against size and count limits.

    Args:
        attachments: List of attachment dictionaries with size information
        from_email: Sender's email address
        to: Recipient's email address
        subject: Email subject
        messageId: Email message ID

    Returns:
        Response if validation fails, None if validation succeeds

    """
    from mxtoai.config import MAX_ATTACHMENT_SIZE_MB, MAX_ATTACHMENTS_COUNT, MAX_TOTAL_ATTACHMENTS_SIZE_MB

    if len(attachments) > MAX_ATTACHMENTS_COUNT:
        rejection_msg = f"""Your email could not be processed due to too many attachments.

Maximum allowed attachments: {MAX_ATTACHMENTS_COUNT}
Number of attachments in your email: {len(attachments)}

Please reduce the number of attachments and try again.

Best,
MX to AI Team"""

        html_rejection = f"""<p>Your email could not be processed due to too many attachments.</p>
<p>Maximum allowed attachments: {MAX_ATTACHMENTS_COUNT}<br>
Number of attachments in your email: {len(attachments)}</p>
<p>Please reduce the number of attachments and try again.</p>
<p>Best regards,<br>MX to AI Team</p>"""

        email_dict = {
            "from": from_email,
            "to": to,
            "subject": f"Re: {subject}",
            "messageId": messageId,
            "references": None,
            "inReplyTo": messageId,
            "cc": None,
        }

        try:
            await send_email_reply(email_dict, rejection_msg, html_rejection)
            logger.info(f"Sent attachment count rejection email to {from_email}")
        except Exception as e:
            logger.error(f"Failed to send attachment count rejection email: {e}")

        return Response(
            content=json.dumps(
                {
                    "message": "Too many attachments",
                    "max_allowed": MAX_ATTACHMENTS_COUNT,
                    "received": len(attachments),
                    "rejection_sent": True,
                }
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
            media_type="application/json",
        )

    total_size_mb = sum(attachment.get("size", 0) for attachment in attachments) / (1024 * 1024)

    for attachment in attachments:
        size_mb = attachment.get("size", 0) / (1024 * 1024)
        if size_mb > MAX_ATTACHMENT_SIZE_MB:
            rejection_msg = f"""Your email could not be processed due to an oversized attachment.

Maximum allowed size per attachment: {MAX_ATTACHMENT_SIZE_MB}MB
Size of attachment '{attachment.get("filename", "unknown")}': {size_mb:.1f}MB

Please reduce the file size and try again.

Best,
MX to AI Team"""

            html_rejection = f"""<p>Your email could not be processed due to an oversized attachment.</p>
<p>Maximum allowed size per attachment: {MAX_ATTACHMENT_SIZE_MB}MB<br>
Size of attachment '{attachment.get("filename", "unknown")}': {size_mb:.1f}MB</p>
<p>Please reduce the file size and try again.</p>
<p>Best regards,<br>MX to AI Team</p>"""

            email_dict = {
                "from": from_email,
                "to": to,
                "subject": f"Re: {subject}",
                "messageId": messageId,
                "references": None,
                "inReplyTo": messageId,
                "cc": None,
            }

            try:
                await send_email_reply(email_dict, rejection_msg, html_rejection)
                logger.info(f"Sent attachment size rejection email to {from_email}")
            except Exception as e:
                logger.error(f"Failed to send attachment size rejection email: {e}")

            return Response(
                content=json.dumps(
                    {
                        "message": "Attachment too large",
                        "filename": attachment.get("filename", "unknown"),
                        "size_mb": size_mb,
                        "max_allowed_mb": MAX_ATTACHMENT_SIZE_MB,
                        "rejection_sent": True,
                    }
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
                media_type="application/json",
            )

    if total_size_mb > MAX_TOTAL_ATTACHMENTS_SIZE_MB:
        rejection_msg = f"""Your email could not be processed due to total attachment size exceeding the limit.

Maximum allowed total size: {MAX_TOTAL_ATTACHMENTS_SIZE_MB}MB
Total size of your attachments: {total_size_mb:.1f}MB

Please reduce the total size of attachments and try again.

Best,
MX to AI Team"""

        html_rejection = f"""<p>Your email could not be processed due to total attachment size exceeding the limit.</p>
<p>Maximum allowed total size: {MAX_TOTAL_ATTACHMENTS_SIZE_MB}MB<br>
Total size of your attachments: {total_size_mb:.1f}MB</p>
<p>Please reduce the total size of attachments and try again.</p>
<p>Best regards,<br>MX to AI Team</p>"""

        email_dict = {
            "from": from_email,
            "to": to,
            "subject": f"Re: {subject}",
            "messageId": messageId,
            "references": None,
            "inReplyTo": messageId,
            "cc": None,
        }

        try:
            await send_email_reply(email_dict, rejection_msg, html_rejection)
            logger.info(f"Sent total attachment size rejection email to {from_email}")
        except Exception as e:
            logger.error(f"Failed to send total attachment size rejection email: {e}")

        return Response(
            content=json.dumps(
                {
                    "message": "Total attachment size too large",
                    "total_size_mb": total_size_mb,
                    "max_allowed_mb": MAX_TOTAL_ATTACHMENTS_SIZE_MB,
                    "rejection_sent": True,
                }
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
            media_type="application/json",
        )

    return None
