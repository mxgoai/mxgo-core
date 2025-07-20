"""
User plan management and Dodo Payments integration.

This module provides functionality to determine user subscription plans
by integrating with the Dodo Payments API.
"""

from datetime import datetime
from email.utils import parseaddr
from typing import Any

import httpx

from mxtoai._logging import get_logger
from mxtoai.config import DODO_API_BASE_URL, DODO_API_KEY, PRO_PLAN_PRODUCT_ID
from mxtoai.schemas import UserPlan

# Configure logging
logger = get_logger(__name__)

# HTTP client timeout configuration
REQUEST_TIMEOUT = 30.0

# HTTP status codes
HTTP_OK = 200


async def get_user_plan(email: str) -> UserPlan:
    """
    Determine user plan based on Dodo Payments subscription status.

    Args:
        email: User's email address

    Returns:
        UserPlan: The user's subscription plan (PRO or BETA)

    Note:
        Falls back to UserPlan.BETA on any errors or missing configuration.

    """
    # Check if Dodo API key is configured
    if not DODO_API_KEY:
        logger.warning("DODO_API_KEY not configured, falling back to BETA plan for all users")
        return UserPlan.BETA

    try:
        # Step 1: Look up customer by email
        customer_id = await _get_customer_id_by_email(email)
        if not customer_id:
            logger.info(f"No customer found for email {email}, returning BETA plan")
            return UserPlan.BETA

        # Step 2: Get active subscriptions for the customer
        latest_subscription = await _get_latest_active_subscription(customer_id)
        if not latest_subscription:
            logger.info(f"No active subscriptions found for customer {customer_id}, returning BETA plan")
            return UserPlan.BETA

        # Step 3: Check if subscription matches PRO plan product ID
        product_id = latest_subscription.get("product_id")
        if PRO_PLAN_PRODUCT_ID and product_id == PRO_PLAN_PRODUCT_ID:
            logger.info(f"User {email} has PRO plan subscription (product_id: {product_id})")
            return UserPlan.PRO
        logger.info(
            f"User {email} subscription does not match PRO plan (product_id: {product_id}), returning BETA plan"
        )

    except Exception as e:
        logger.error(f"Error determining user plan for {email}: {e}")
        logger.warning(f"Falling back to BETA plan for user {email} due to error")

    return UserPlan.BETA


async def _get_customer_id_by_email(email: str) -> str | None:
    """
    Look up customer ID by email address using Dodo Payments API.

    Args:
        email: Customer's email address

    Returns:
        str | None: Customer ID if found, None otherwise

    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(
                f"{DODO_API_BASE_URL}/customers",
                headers={"Authorization": f"Bearer {DODO_API_KEY}", "Content-Type": "application/json"},
                params={"email": email},
            )

            if response.status_code == HTTP_OK:
                data = response.json()
                customers = data.get("items", [])

                if customers:
                    customer = customers[0]  # Take the first matching customer
                    customer_id = customer.get("customer_id")
                    logger.debug(f"Found customer {customer_id} for email {email}")
                    return customer_id
                logger.debug(f"No customers found for email {email}")
                return None
            logger.error(f"Dodo Payments API error for customer lookup: {response.status_code} - {response.text}")
            return None

    except httpx.TimeoutException:
        logger.error(f"Timeout while looking up customer for email {email}")
        return None
    except Exception as e:
        logger.error(f"Error looking up customer for email {email}: {e}")
        return None


async def _get_latest_active_subscription(customer_id: str) -> dict[str, Any] | None:
    """
    Get the latest active subscription for a customer.

    Args:
        customer_id: Customer's ID from Dodo Payments

    Returns:
        dict | None: Latest active subscription data if found, None otherwise

    """
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(
                f"{DODO_API_BASE_URL}/subscriptions",
                headers={"Authorization": f"Bearer {DODO_API_KEY}", "Content-Type": "application/json"},
                params={"customer_id": customer_id, "status": "active"},
            )

            if response.status_code == HTTP_OK:
                data = response.json()
                subscriptions = data.get("items", [])

                if subscriptions:
                    # Sort by created_at to get the latest subscription
                    sorted_subscriptions = sorted(
                        subscriptions,
                        key=lambda x: datetime.fromisoformat(x.get("created_at", "1970-01-01T00:00:00Z")),
                        reverse=True,
                    )
                    latest_subscription = sorted_subscriptions[0]
                    logger.debug(
                        f"Found {len(subscriptions)} active subscriptions for customer {customer_id}, using latest: {latest_subscription.get('subscription_id')}"
                    )
                    return latest_subscription
                logger.debug(f"No active subscriptions found for customer {customer_id}")
                return None
            logger.error(f"Dodo Payments API error for subscription lookup: {response.status_code} - {response.text}")
            return None

    except httpx.TimeoutException:
        logger.error(f"Timeout while looking up subscriptions for customer {customer_id}")
        return None
    except Exception as e:
        logger.error(f"Error looking up subscriptions for customer {customer_id}: {e}")
        return None


def normalize_email(email_address: str) -> str:
    """Normalize email address by removing +alias and lowercasing domain."""
    name, addr = parseaddr(email_address)
    if not addr:
        return email_address.lower()  # Fallback for unparseable addresses

    # Check if addr contains @
    if "@" not in addr:
        return email_address.lower()  # Fallback for invalid addresses

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
        return ""  # Should not happen for valid emails
