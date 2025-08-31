import asyncio
import json
import os
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import Response, status

from mxgo import exceptions
from mxgo._logging import get_logger
from mxgo.config import (
    MAX_ATTACHMENT_SIZE_MB,
    MAX_ATTACHMENTS_COUNT,
    MAX_TOTAL_ATTACHMENTS_SIZE_MB,
    PERIOD_EXPIRY,
    RATE_LIMIT_PER_DOMAIN_HOUR,
    RATE_LIMITS_BY_PLAN,
)
from mxgo.dependencies import processing_instructions_resolver
from mxgo.email_sender import generate_message_id, send_email_reply
from mxgo.schemas import UserPlan
from mxgo.user import get_domain_from_email, normalize_email
from mxgo.whitelist import get_whitelist_signup_url, is_email_whitelisted, trigger_automatic_verification

logger = get_logger(__name__)

# Globals to be initialized from api.py
redis_client: aioredis.Redis | None = None
email_provider_domain_set: set[str] = set()  # Still useful for the domain check logic


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
    key_type: str,  # "email" or "domain"
    identifier: str,
    plan_or_domain_limits: dict[
        str, dict[str, int]
    ],  # e.g., RATE_LIMITS_BY_PLAN[RateLimitPlan.BETA] or RATE_LIMIT_PER_DOMAIN_HOUR
    current_dt: datetime,
    plan_name_for_key: str = "",  # e.g. "beta" or "" for domain
) -> str | None:
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
        return None  # Fail open if Redis is not ready

    for period_name, config in plan_or_domain_limits.items():
        limit = config["limit"]
        # Use fixed expiry from PERIOD_EXPIRY, not config["expiry_seconds"] if that was for the period itself
        # The key identifies the *start* of the window
        time_bucket = get_current_timestamp_for_period(period_name, current_dt)

        redis_key_parts = ["rate_limit", key_type, identifier]
        if plan_name_for_key:  # Add plan to key for email limits
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
                return period_name  # e.g., "hour", "day", "month"
        except aioredis.RedisError as e:
            logger.error(f"Redis error during rate limit check for key {redis_key}: {e}")
            return None  # Fail open on Redis error to avoid blocking legitimate requests

    return None


async def get_current_usage_redis(
    key_type: str,  # "email" or "domain"
    identifier: str,
    plan_or_domain_limits: dict[str, dict[str, int]],
    current_dt: datetime,
    plan_name_for_key: str = "",
) -> dict[str, dict[str, int]]:
    """
    Get current usage counts from Redis without incrementing.

    Args:
        key_type: "email" or "domain".
        identifier: Normalized email or domain string.
        plan_or_domain_limits: Dictionary defining limits for "hour", "day", "month".
        current_dt: Current datetime object (timezone-aware).
        plan_name_for_key: String representation of the plan for key namespacing.

    Returns:
        Dictionary with period names as keys and usage info as values.
        Each value contains: {"current_usage": int, "max_usage_allowed": int}

    """
    if redis_client is None:
        logger.error("Redis client not initialized for usage checking.")
        return {}

    usage_info = {}

    for period_name, config in plan_or_domain_limits.items():
        limit = config["limit"]
        time_bucket = get_current_timestamp_for_period(period_name, current_dt)

        redis_key_parts = ["rate_limit", key_type, identifier]
        if plan_name_for_key:
            redis_key_parts.append(plan_name_for_key)
        redis_key_parts.extend([period_name, time_bucket])
        redis_key = ":".join(redis_key_parts)

        try:
            current_count = await redis_client.get(redis_key)
            current_usage = int(current_count) if current_count else 0

            usage_info[period_name] = {"current_usage": current_usage, "max_usage_allowed": limit}

            logger.debug(
                f"Usage check for {key_type} '{identifier}' (Plan: '{plan_name_for_key if plan_name_for_key else 'N/A'}'): "
                f"Period '{period_name}', Current usage: {current_usage}/{limit}. Key: {redis_key}"
            )

        except aioredis.RedisError as e:
            logger.error(f"Redis error during usage check for key {redis_key}: {e}")
            # Return zero usage on error to fail gracefully
            usage_info[period_name] = {"current_usage": 0, "max_usage_allowed": limit}

    return usage_info


async def send_rate_limit_rejection_email(
    from_email: str, to: str, subject: str | None, message_id: str | None, limit_type: str, plan: UserPlan | None = None
) -> None:
    """Send a rejection email for rate limit exceeded."""
    rejection_subject = f"Re: {subject}" if subject else "Usage Limit Exceeded"
    rejection_text = f"""Your email could not be processed because the usage limit has been exceeded ({limit_type}).
Please try again after some time.

Best,
MXGo Team"""
    html_rejection_text = f"""<p>Your email could not be processed because the usage limit has been exceeded ({limit_type}).</p>
<p>Please try again after some time.</p>
<p>Best regards,<br>MXGo Team</p>"""

    # Add upgrade message for BETA/FREE users only
    if plan and plan in [UserPlan.BETA, UserPlan.FREE]:
        pro_limits = RATE_LIMITS_BY_PLAN.get(UserPlan.PRO, {})
        upgrade_message = f"""

---

💡 Need more capacity? Upgrade to PRO plan for higher limits:
• PRO Plan: {pro_limits.get("hour", {}).get("limit", 50)} emails/hour, {pro_limits.get("day", {}).get("limit", 100)} emails/day, {pro_limits.get("month", {}).get("limit", 1000)} emails/month
• Visit https://mxgo.ai to upgrade

Upgrade now to continue using MXGo without interruption!"""

        html_upgrade_message = f"""
<hr>
<div style="background: #e8f4fd; border: 1px solid #bee5eb; color: #0c5460; padding: 15px; border-radius: 6px; margin: 20px 0;">
    <strong>💡 Need more capacity? Upgrade to PRO plan for higher limits:</strong><br>
    • PRO Plan: {pro_limits.get("hour", {}).get("limit", 50)} emails/hour, {pro_limits.get("day", {}).get("limit", 100)} emails/day, {pro_limits.get("month", {}).get("limit", 1000)} emails/month<br>
    • Visit <a href="https://mxgo.ai">https://mxgo.ai</a> to upgrade<br><br>
    <strong>Upgrade now to continue using MXGo without interruption!</strong>
</div>"""

        rejection_text += upgrade_message
        html_rejection_text += html_upgrade_message

    email_dict = {
        "from": from_email,
        "to": to,
        "subject": rejection_subject,
        "messageId": message_id,
        "references": None,
        "inReplyTo": message_id,
        "cc": None,
    }
    try:
        await send_email_reply(email_dict, rejection_text, html_rejection_text)
        logger.info(f"Sent rate limit ({limit_type}) rejection email to {from_email}")
    except Exception as e:
        logger.error(f"Failed to send rate limit rejection email to {from_email}: {e}")


async def validate_rate_limits(
    from_email: str, to: str, subject: str | None, message_id: str | None, plan: UserPlan
) -> Response | None:
    """
    Validate incoming email against defined rate limits based on the plan, using Redis.
    """
    if redis_client is None:  # Should not happen if initialized correctly
        logger.warning("Redis client not initialized. Skipping rate limit check.")
        return None

    normalized_user_email = normalize_email(from_email)
    email_domain = get_domain_from_email(normalized_user_email)
    current_dt = datetime.now(timezone.utc)  # Use timezone-aware datetime

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
            plan_name_for_key=plan.value,
        )
        if email_limit_exceeded_period:
            limit_type_msg = f"email {email_limit_exceeded_period} for {plan.value} plan"
            await send_rate_limit_rejection_email(from_email, to, subject, message_id, limit_type_msg, plan)
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
            plan_or_domain_limits=RATE_LIMIT_PER_DOMAIN_HOUR,  # This needs to be a dict of periods
            current_dt=current_dt,
        )
        if domain_limit_exceeded_period:  # This will be "hour" if exceeded
            limit_type_msg = f"domain {domain_limit_exceeded_period}"
            await send_rate_limit_rejection_email(from_email, to, subject, message_id, limit_type_msg, plan)
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


async def validate_idempotency(
    from_email: str,
    to: str,
    subject: str,
    date: str,
    html_content: str,
    text_content: str,
    files_count: int,
    message_id: str | None = None,
) -> tuple[Response | None, str]:
    """
    Validate email idempotency and generate deterministic message ID if needed.

    Args:
        from_email: Sender's email address
        to: Recipient's email address
        subject: Email subject
        date: Email date
        html_content: HTML content of the email
        text_content: Text content of the email
        files_count: Number of attached files
        message_id: Existing message ID (optional)

    Returns:
        Tuple of (Response if validation fails, message_id)

    """
    # Generate deterministic messageId if not provided
    if not message_id:
        message_id = generate_message_id(
            from_email=from_email,
            to=to,
            subject=subject or "",
            date=date or "",
            html_content=html_content or "",
            text_content=text_content or "",
            files_count=files_count,
        )
        logger.info(f"Generated deterministic message ID: {message_id}")

    # Check for duplicate processing using Redis (idempotency check)
    redis_key_queued = f"email_queued:{message_id}"
    redis_key_processed = f"email_processed:{message_id}"

    if redis_client:
        try:
            # Check if already queued
            if await redis_client.get(redis_key_queued):
                logger.warning(f"Email with messageId {message_id} already queued for processing")
                return Response(
                    content=json.dumps(
                        {
                            "message": "Email already queued for processing",
                            "messageId": message_id,
                            "status": "duplicate_queued",
                        }
                    ),
                    status_code=status.HTTP_409_CONFLICT,
                    media_type="application/json",
                ), message_id

            # Check if already processed
            if await redis_client.get(redis_key_processed):
                logger.warning(f"Email with messageId {message_id} already processed")
                return Response(
                    content=json.dumps(
                        {"message": "Email already processed", "messageId": message_id, "status": "duplicate_processed"}
                    ),
                    status_code=status.HTTP_409_CONFLICT,
                    media_type="application/json",
                ), message_id

            # Mark as queued (expires in 1 hour)
            await redis_client.setex(redis_key_queued, 3600, "1")
            logger.info(f"Marked email {message_id} as queued in Redis")

        except Exception as redis_error:
            logger.error(f"Redis idempotency check failed: {redis_error}")
            # Continue processing even if Redis fails
    else:
        logger.warning("Redis not available for idempotency checks")

    return None, message_id


def check_task_idempotency(message_id: str) -> bool:
    """
    Check if an email task has already been processed.

    Args:
        message_id: The message ID to check

    Returns:
        True if already processed, False if not processed

    """
    if not redis_client or not message_id:
        return False

    redis_key_processed = f"email_processed:{message_id}"

    try:
        # Check if already processed
        if asyncio.run(redis_client.get(redis_key_processed)):
            logger.warning(f"Email with messageId {message_id} already processed, skipping duplicate processing")
            return True
    except Exception as redis_error:
        logger.error(f"Redis idempotency check failed in task: {redis_error}")
        # Continue processing even if Redis fails

    return False


def mark_email_as_processed(message_id: str) -> None:
    """
    Mark an email as successfully processed in Redis.

    Args:
        message_id: The message ID to mark as processed

    """
    if not redis_client or not message_id:
        return

    redis_key_processed = f"email_processed:{message_id}"
    redis_key_queued = f"email_queued:{message_id}"

    try:
        # Mark as processed (expires in 24 hours)
        asyncio.run(
            asyncio.gather(redis_client.setex(redis_key_processed, 86400, "1"), redis_client.delete(redis_key_queued))
        )
        logger.info(f"Marked email {message_id} as processed in Redis")
    except Exception as redis_error:
        logger.error(f"Failed to mark email as processed in Redis: {redis_error}")


async def validate_api_key(api_key: str) -> Response | None:
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


async def validate_email_whitelist(from_email: str, to: str, subject: str, message_id: str | None) -> Response | None:
    """
    Validate email whitelist to ensure only authorized senders can use the service.

    Args:
        from_email: The sender's email address
        to: The recipient's email address
        subject: The email subject
        message_id: Optional message ID for tracking

    Returns:
        Optional[Response]: Error response if validation fails, None if validation passes

    """
    # Extract domain from sender's email
    email_domain = get_domain_from_email(from_email)

    # Check if email is from major email provider
    is_major_provider = email_domain in email_provider_domain_set

    # Check Supabase whitelist for all emails
    exists_in_whitelist, is_verified = await is_email_whitelisted(from_email)

    # Allow if email is from major provider OR exists and is verified in the Supabase whitelist.
    if is_major_provider:
        logger.info(f"Email allowed from major email provider: {from_email} (domain: {email_domain})")
        return None
    if exists_in_whitelist and is_verified:
        logger.info(f"Email allowed from Supabase whitelist: {from_email} (verified)")
        return None

    # For non-major providers that are not verified, trigger automatic verification
    # and STOP email processing until they verify
    logger.info(
        f"Triggering automatic verification for {from_email} (exists={exists_in_whitelist}, verified={is_verified})"
    )

    # Trigger automatic verification in the background
    verification_triggered = False
    try:
        verification_triggered = await trigger_automatic_verification(from_email)
        if verification_triggered:
            logger.info(f"Successfully triggered automatic verification for {from_email}")
        else:
            logger.warning(f"Failed to trigger automatic verification for {from_email}")
    except Exception as e:
        logger.error(f"Error triggering automatic verification for {from_email}: {e}")

    # Determine rejection message based on verification status and outcome
    if verification_triggered:
        # Verification email was sent successfully
        rejection_msg = f"""Your email could not be processed because your domain is not automatically whitelisted.

Major email providers (Gmail, Outlook, Yahoo, etc.) are automatically whitelisted, but custom domains require verification.

🚀 GOOD NEWS: We've automatically started the verification process for you!

📧 CHECK YOUR EMAIL: You should receive a verification email at {from_email} within the next few minutes.

✅ NEXT STEPS:
1. Click the verification link in the email we just sent
2. Once verified, simply resend your original email to this address
3. Your email will then be processed normally

⚠️ IMPORTANT: You must verify your email first, then resend your request for it to be processed.

Best,
MXGo Team"""

        html_rejection = f"""<p>Your email could not be processed because your domain is not automatically whitelisted.</p>
<p>Major email providers (Gmail, Outlook, Yahoo, etc.) are automatically whitelisted, but custom domains require verification.</p>

<div style="background: #d4edda; border: 1px solid #c3e6cb; color: #155724; padding: 15px; border-radius: 6px; margin: 20px 0;">
    <strong>🚀 GOOD NEWS:</strong> We've automatically started the verification process for you!
</div>

<div style="background: #e2e3e5; border: 1px solid #d6d8db; color: #383d41; padding: 15px; border-radius: 6px; margin: 20px 0;">
    <strong>📧 CHECK YOUR EMAIL:</strong> You should receive a verification email at <strong>{from_email}</strong> within the next few minutes.
</div>

<p><strong>✅ NEXT STEPS:</strong></p>
<ol>
    <li>Click the verification link in the email we just sent</li>
    <li>Once verified, simply resend your original email to this address</li>
    <li>Your email will then be processed normally</li>
</ol>

<div style="background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; padding: 15px; border-radius: 6px; margin: 20px 0;">
    <strong>⚠️ IMPORTANT:</strong> You must verify your email first, then resend your request for it to be processed.
</div>

<p>Best regards,<br>MXGo Team</p>"""
    else:
        # Verification email failed to send - fallback to manual signup
        signup_url = get_whitelist_signup_url()
        rejection_msg = f"""Your email could not be processed because your domain is not automatically whitelisted.

Major email providers (Gmail, Outlook, Yahoo, etc.) are automatically whitelisted, but custom domains require manual approval.

We attempted to automatically send you a verification email, but it failed. Please visit {signup_url} to manually request access.

Once your email is verified, you can resend your email for processing.

Best,
MXGo Team"""

        html_rejection = f"""<p>Your email could not be processed because your domain is not automatically whitelisted.</p>
<p>Major email providers (Gmail, Outlook, Yahoo, etc.) are automatically whitelisted, but custom domains require manual approval.</p>
<p>We attempted to automatically send you a verification email, but it failed. Please visit <a href="{signup_url}">{signup_url}</a> to manually request access.</p>
<p>Once your email is verified, you can resend your email for processing.</p>
<p>Best regards,<br>MXGo Team</p>"""

    # Send rejection email
    email_dict = {
        "from": from_email,  # Original sender becomes recipient
        "to": to,  # Original recipient becomes sender
        "subject": f"Re: {subject}",
        "messageId": message_id,
        "references": None,
        "inReplyTo": message_id,
        "cc": None,
    }

    try:
        await send_email_reply(email_dict, rejection_msg, html_rejection)
        logger.info(
            f"Sent verification instruction email to {from_email} (verification_triggered={verification_triggered})"
        )
    except Exception as e:
        logger.error(f"Failed to send verification instruction email: {e}")

    # Return error response to stop email processing
    return Response(
        content=json.dumps(
            {
                "message": "Email verification required - check your email for verification instructions",
                "email": from_email,
                "verification_triggered": verification_triggered,
                "exists_in_whitelist": exists_in_whitelist,
                "is_verified": is_verified,
                "next_action": "verify_email_then_resend",
            }
        ),
        status_code=status.HTTP_403_FORBIDDEN,
        media_type="application/json",
    )


async def validate_email_handle(
    to: str, from_email: str, subject: str, message_id: str | None
) -> tuple[Response | None, str | None]:
    """
    Validate the email handle to ensure it's supported and extract the handle.

    Args:
        to: Recipient's email address
        from_email: Sender's email address
        subject: Email subject
        message_id: Optional message ID for tracking

    Returns:
        tuple[Optional[Response], Optional[str]]: (Error response if validation fails, extracted handle)

    """
    raw_handle = to.split("@")[0].lower()

    # Strip everything after '+' if present
    if "+" in raw_handle:
        handle = raw_handle.split("+")[0]
        logger.info(f"Stripped handle suffix: '{raw_handle}' -> '{handle}'")
    else:
        handle = raw_handle

    try:
        _ = processing_instructions_resolver(handle)
    except exceptions.UnspportedHandleError:
        rejection_msg = "This email alias is not supported. Please visit https://mxgo.ai/docs/email-handles to learn about supported email handles."

        # Create email dict with proper format
        email_dict = {
            "from": from_email,  # Original sender becomes recipient
            "to": to,  # Original recipient becomes sender
            "subject": f"Re: {subject}",
            "messageId": message_id,
            "references": None,
            "inReplyTo": message_id,
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
    attachments: list[dict], from_email: str, to: str, subject: str, message_id: str | None
) -> Response | None:
    """
    Validate email attachments for security and size constraints.

    Args:
        attachments: List of attachment dictionaries
        from_email: Sender's email address
        to: Recipient's email address
        subject: Email subject
        message_id: Optional message ID for tracking

    Returns:
        Optional[Response]: Error response if validation fails, None if validation passes

    """
    if len(attachments) > MAX_ATTACHMENTS_COUNT:
        rejection_msg = f"""Your email could not be processed due to too many attachments.

Maximum allowed attachments: {MAX_ATTACHMENTS_COUNT}
Number of attachments in your email: {len(attachments)}

Please reduce the number of attachments and try again.

Best,
MXGo Team"""

        html_rejection = f"""<p>Your email could not be processed due to too many attachments.</p>
<p>Maximum allowed attachments: {MAX_ATTACHMENTS_COUNT}<br>
Number of attachments in your email: {len(attachments)}</p>
<p>Please reduce the number of attachments and try again.</p>
<p>Best regards,<br>MXGo Team</p>"""

        email_dict = {
            "from": from_email,
            "to": to,
            "subject": f"Re: {subject}",
            "messageId": message_id,
            "references": None,
            "inReplyTo": message_id,
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

    total_size_mb = 0
    for attachment in attachments:
        size_mb = attachment.get("size", 0) / (1024 * 1024)
        if size_mb > MAX_ATTACHMENT_SIZE_MB:
            rejection_msg = f"""Your email could not be processed due to an oversized attachment.

Maximum allowed size per attachment: {MAX_ATTACHMENT_SIZE_MB}MB
Size of attachment '{attachment.get("filename", "unknown")}': {size_mb:.1f}MB

Please reduce the file size and try again.

Best,
MXGo Team"""

            html_rejection = f"""<p>Your email could not be processed due to an oversized attachment.</p>
<p>Maximum allowed size per attachment: {MAX_ATTACHMENT_SIZE_MB}MB<br>
Size of attachment '{attachment.get("filename", "unknown")}': {size_mb:.1f}MB</p>
<p>Please reduce the file size and try again.</p>
<p>Best regards,<br>MXGo Team</p>"""

            email_dict = {
                "from": from_email,
                "to": to,
                "subject": f"Re: {subject}",
                "messageId": message_id,
                "references": None,
                "inReplyTo": message_id,
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
        total_size_mb += size_mb

    if total_size_mb > MAX_TOTAL_ATTACHMENTS_SIZE_MB:
        rejection_msg = f"""Your email could not be processed due to total attachment size exceeding the limit.

Maximum allowed total size: {MAX_TOTAL_ATTACHMENTS_SIZE_MB}MB
Total size of your attachments: {total_size_mb:.1f}MB

Please reduce the total size of attachments and try again.

Best,
MXGo Team"""

        html_rejection = f"""<p>Your email could not be processed due to total attachment size exceeding the limit.</p>
<p>Maximum allowed total size: {MAX_TOTAL_ATTACHMENTS_SIZE_MB}MB<br>
Total size of your attachments: {total_size_mb:.1f}MB</p>
<p>Please reduce the total size of attachments and try again.</p>
<p>Best regards,<br>MXGo Team</p>"""

        email_dict = {
            "from": from_email,
            "to": to,
            "subject": f"Re: {subject}",
            "messageId": message_id,
            "references": None,
            "inReplyTo": message_id,
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
