import json
import os

# import shelve # Removed shelve
from datetime import datetime, timezone  # Added timezone
from email.utils import parseaddr
from typing import Optional

import redis.asyncio as aioredis  # Added redis
from fastapi import Response, status

from mxtoai import exceptions
from mxtoai._logging import get_logger
from mxtoai.dependencies import processing_instructions_resolver
from mxtoai.email_sender import send_email_reply
from mxtoai.schemas import RateLimitPlan
from mxtoai.whitelist import get_whitelist_signup_url, is_email_whitelisted

logger = get_logger(__name__)

# Globals to be initialized from api.py
redis_client: Optional[aioredis.Redis] = None
email_provider_domain_set: set[str] = set() # Still useful for the domain check logic

# Rate limit settings
RATE_LIMITS_BY_PLAN = {
    RateLimitPlan.BETA: {
        "hour": {"limit": 20, "period_seconds": 3600, "expiry_seconds": 3600 * 2}, # 2hr expiry for 1hr window
        "day": {"limit": 50, "period_seconds": 86400, "expiry_seconds": 86400 + 3600}, # 25hr expiry for 24hr window
        "month": {"limit": 300, "period_seconds": 30 * 86400, "expiry_seconds": (30 * 86400) + 86400} # 31day expiry for 30day window
    }
}
RATE_LIMIT_PER_DOMAIN_HOUR = { # Consistent structure for domain limits
    "hour": {"limit": 50, "period_seconds": 3600, "expiry_seconds": 3600 * 2}
}

# TTLs for different periods (approximate for safety)
PERIOD_EXPIRY = {
    "hour": 3600 * 2,  # 2 hours
    "day": 86400 + 3600,  # 25 hours
    "month": 30 * 86400 + 86400, # 31 days
}


def get_current_timestamp_for_period(period_name: str, dt: datetime) -> str:
    if period_name == "hour":
        return dt.strftime("%Y%m%d%H")
    if period_name == "day":
        return dt.strftime("%Y%m%d")
    if period_name == "month":
        return dt.strftime("%Y%m")
    msg = f"Unknown period name: {period_name}"
    raise ValueError(msg)


async def check_rate_limit_redis(
    key_type: str, # "email" or "domain"
    identifier: str,
    plan_or_domain_limits: dict[str, dict[str, int]], # e.g., RATE_LIMITS_BY_PLAN[RateLimitPlan.BETA] or RATE_LIMIT_PER_DOMAIN_HOUR
    current_dt: datetime,
    plan_name_for_key: str = "" # e.g. "beta" or "" for domain
) -> Optional[str]:
    """
    Checks and updates rate limits using Redis.

    Args:
        key_type: "email" or "domain".
        identifier: Normalized email or domain string.
        plan_or_domain_limits: Dictionary defining limits for "hour", "day", "month".
                               Each entry is a dict with "limit" and "expiry_seconds".
        current_dt: Current datetime object (timezone-aware).
        plan_name_for_key: String representation of the plan (e.g. "beta") for key namespacing.

    Returns:
        A string describing the limit exceeded (e.g., "hour") or None if within limits.

    """
    if redis_client is None:
        logger.error("Redis client not initialized for rate limiting.")
        return None # Fail open if Redis is not ready

    for period_name, config in plan_or_domain_limits.items():
        limit = config["limit"]
        # Use fixed expiry from PERIOD_EXPIRY, not config["expiry_seconds"] if that was for the period itself
        # The key identifies the *start* of the window
        time_bucket = get_current_timestamp_for_period(period_name, current_dt)

        redis_key_parts = ["rate_limit", key_type, identifier]
        if plan_name_for_key: # Add plan to key for email limits
            redis_key_parts.append(plan_name_for_key)
        redis_key_parts.extend([period_name, time_bucket])
        redis_key = ":".join(redis_key_parts)

        try:
            async with redis_client.pipeline(transaction=True) as pipe:
                pipe.incr(redis_key)
                pipe.expire(redis_key, PERIOD_EXPIRY[period_name])
                results = await pipe.execute()

            current_count = results[0]

            # Log current count for the identifier and period
            logger.info(
                f"Rate limit check for {key_type} '{identifier}' (Plan: '{plan_name_for_key if plan_name_for_key else 'N/A'}'): "
                f"Period '{period_name}' (bucket: {time_bucket}), Current count: {current_count}/{limit}. Key: {redis_key}"
            )

            if current_count > limit:
                logger.warning(
                    f"Rate limit EXCEEDED for {key_type} '{identifier}' (Plan: '{plan_name_for_key if plan_name_for_key else 'N/A'}'): "
                    f"Period '{period_name}', Count: {current_count}/{limit}. Key: {redis_key}"
                )
                return period_name # e.g., "hour", "day", "month"
        except aioredis.RedisError as e:
            logger.error(f"Redis error during rate limit check for key {redis_key}: {e}")
            return None # Fail open on Redis error to avoid blocking legitimate requests

    return None


def normalize_email(email_address: str) -> str:
    """Normalize email address by removing +alias and lowercasing domain."""
    name, addr = parseaddr(email_address)
    if not addr:
        return email_address.lower()  # Fallback for unparseable addresses

    local_part, domain_part = addr.split("@", 1)
    domain_part = domain_part.lower()

    # Remove +alias from local_part
    if "+" in local_part:
        local_part = local_part.split("+", 1)[0]

    return f"{local_part}@{domain_part}"


def get_domain_from_email(email_address: str) -> str:
    """Extract domain from email address."""
    try:
        return email_address.split("@", 1)[1].lower()
    except IndexError:
        return "" # Should not happen for valid emails


async def send_rate_limit_rejection_email(
    from_email: str, to: str, subject: Optional[str], messageId: Optional[str], limit_type: str
) -> None:
    """Send a rejection email for rate limit exceeded."""
    rejection_subject = f"Re: {subject}" if subject else "Usage Limit Exceeded"
    rejection_text = f"""Your email could not be processed because the usage limit has been exceeded ({limit_type}).
Please try again after some time.

Best,
MX to AI Team"""
    html_rejection_text = f"""<p>Your email could not be processed because the usage limit has been exceeded ({limit_type}).</p>
<p>Please try again after some time.</p>
<p>Best regards,<br>MX to AI Team</p>"""

    email_dict = {
        "from": from_email,
        "to": to,
        "subject": rejection_subject,
        "messageId": messageId,
        "references": None,
        "inReplyTo": messageId,
        "cc": None,
    }
    try:
        await send_email_reply(email_dict, rejection_text, html_rejection_text)
        logger.info(f"Sent rate limit ({limit_type}) rejection email to {from_email}")
    except Exception as e:
        logger.error(f"Failed to send rate limit rejection email to {from_email}: {e}")


async def validate_rate_limits(
    from_email: str, to: str, subject: Optional[str], messageId: Optional[str], plan: RateLimitPlan
) -> Optional[Response]:
    """
    Validate incoming email against defined rate limits based on the plan, using Redis.
    """
    if redis_client is None: # Should not happen if initialized correctly
        logger.warning("Redis client not initialized. Skipping rate limit check.")
        return None

    normalized_user_email = normalize_email(from_email)
    email_domain = get_domain_from_email(normalized_user_email)
    current_dt = datetime.now(timezone.utc) # Use timezone-aware datetime

    # 1. Per-email limits based on plan
    plan_email_limits_config = RATE_LIMITS_BY_PLAN.get(plan)
    if not plan_email_limits_config:
        logger.error(f"Rate limits for plan {plan.value} not configured. Skipping email rate limit check.")
    else:
        email_limit_exceeded_period = await check_rate_limit_redis(
            key_type="email",
            identifier=normalized_user_email,
            plan_or_domain_limits=plan_email_limits_config,
            current_dt=current_dt,
            plan_name_for_key=plan.value
        )
        if email_limit_exceeded_period:
            limit_type_msg = f"email {email_limit_exceeded_period} for {plan.value} plan"
            await send_rate_limit_rejection_email(from_email, to, subject, messageId, limit_type_msg)
            return Response(
                content=json.dumps(
                    {
                        "message": f"Rate limit exceeded ({limit_type_msg}). Please try again later.",
                        "status": "error",
                    }
                ),
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
            )

    # 2. Per-domain limits (if not in provider list)
    if email_domain and email_domain not in email_provider_domain_set:
        # Domain limits are currently only hourly
        domain_limit_exceeded_period = await check_rate_limit_redis(
            key_type="domain",
            identifier=email_domain,
            plan_or_domain_limits=RATE_LIMIT_PER_DOMAIN_HOUR, # This needs to be a dict of periods
            current_dt=current_dt
        )
        if domain_limit_exceeded_period: # This will be "hour" if exceeded
            limit_type_msg = f"domain {domain_limit_exceeded_period}"
            await send_rate_limit_rejection_email(from_email, to, subject, messageId, limit_type_msg)
            return Response(
                content=json.dumps(
                    {
                        "message": f"Rate limit exceeded ({limit_type_msg}). Please try again later.",
                        "status": "error",
                    }
                ),
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                media_type="application/json",
            )

    return None


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

    Major email providers are temporarily whitelisted and bypass the Supabase whitelist check.

    Args:
        from_email: Sender's email address
        to: Recipient's email address
        subject: Email subject
        messageId: Email message ID

    Returns:
        Response if validation fails, None if validation succeeds

    """
    # Extract domain from sender's email
    email_domain = get_domain_from_email(from_email)

    # Skip whitelist validation for major email providers
    if email_domain in email_provider_domain_set:
        logger.info(f"Skipping whitelist validation for major email provider: {from_email} (domain: {email_domain})")
        return None

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
    try:
        _ = processing_instructions_resolver(handle)
    except exceptions.UnspportedHandleException:
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
