"""
CancelSubscriptionTool for handling subscription cancellation requests.

This tool integrates with Dodo Payments API to provide users with access to their
customer portal for subscription management.
"""

from datetime import datetime
from typing import Any, ClassVar

import requests
from smolagents import Tool

from mxtoai._logging import get_logger
from mxtoai.config import DODO_API_BASE_URL, DODO_API_KEY, PRO_PLAN_PRODUCT_ID
from mxtoai.schemas import UserPlan

logger = get_logger(__name__)

REQUEST_TIMEOUT = 30.0
HTTP_OK = 200


class CancelSubscriptionTool(Tool):
    """
    Tool for handling subscription cancellation requests via Dodo Payments API.

    This tool:
    1. Verifies the user has an active PRO subscription
    2. Creates a customer portal session via Dodo Payments API
    3. Returns the portal URL for subscription management
    """

    name = "cancel_subscription_tool"
    description = """
    Processes subscription cancellation requests by checking user subscription status
    and providing customer portal access. Use when users want to cancel their subscription.

    Args:
        user_email (str): Email address of the user requesting cancellation

    Returns:
        dict: Contains status, message, and portal_url (if successful)
    """

    inputs: ClassVar[dict[str, dict[str, str]]] = {
        "user_email": {"type": "string", "description": "Email address of the user requesting cancellation"}
    }

    output_type = "object"

    def __init__(self):
        super().__init__()
        if not DODO_API_KEY:
            logger.warning("DODO_API_KEY not configured - CancelSubscriptionTool may not work properly")

    def forward(self, user_email: str) -> dict[str, Any]:
        """
        Process subscription cancellation request.

        Args:
            user_email: Email address of the user requesting cancellation

        Returns:
            dict: Result containing portal URL or error message

        """
        result = {"success": False, "has_subscription": False, "error_message": None, "portal_url": None}

        try:
            # Validate input
            if not user_email or not user_email.strip():
                result["error_message"] = "Invalid email address provided"
                return result

            user_email = user_email.strip()
            logger.info(f"Processing cancellation request for {user_email}")

            # Check if Dodo API key is configured
            if not DODO_API_KEY:
                logger.error("DODO_API_KEY not configured")
                result["error_message"] = "Subscription management is temporarily unavailable. Please contact support."
                return result

            # Step 1: Check user's subscription status
            user_plan = self._get_user_plan(user_email)
            if user_plan != UserPlan.PRO:
                logger.info(f"User {user_email} does not have PRO subscription (plan: {user_plan.value})")
                result["success"] = True
                result["user_plan"] = user_plan.value
                return result

            # Step 2: Get customer ID for portal creation
            customer_id = self._get_customer_id_by_email(user_email)
            if not customer_id:
                logger.warning(f"Customer ID not found for {user_email} despite having PRO plan")
                result["has_subscription"] = True
                result["error_message"] = "Unable to locate your customer account. Please contact support."
                return result

            # Step 3: Create customer portal session
            portal_url = self._create_customer_portal_session(customer_id)
            if not portal_url:
                logger.error(f"Failed to create portal session for customer {customer_id}")
                result["has_subscription"] = True
                result["error_message"] = "Unable to create portal session. Please contact support."
                result["customer_id"] = customer_id
                return result

            logger.info(f"Successfully created portal session for {user_email}")
            result["success"] = True
            result["has_subscription"] = True
            result["portal_url"] = portal_url
            result["customer_id"] = customer_id
        except Exception as e:
            logger.error(f"Unexpected error processing cancellation request for {user_email}: {e}")
            result["error_message"] = "An unexpected error occurred. Please contact support."

        return result

    def _get_user_plan(self, email: str) -> UserPlan:
        """
        Determine user plan based on Dodo Payments subscription status.

        Args:
            email: User's email address

        Returns:
            UserPlan: The user's subscription plan (PRO or BETA)

        """
        # Check if Dodo API key is configured
        if not DODO_API_KEY:
            logger.warning("DODO_API_KEY not configured, falling back to BETA plan for all users")
            return UserPlan.BETA

        try:
            # Step 1: Look up customer by email
            customer_id = self._get_customer_id_by_email(email)
            if not customer_id:
                logger.info(f"No customer found for email {email}, returning BETA plan")
                return UserPlan.BETA

            # Step 2: Get active subscriptions for the customer
            latest_subscription = self._get_latest_active_subscription(customer_id)
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

    def _get_customer_id_by_email(self, email: str) -> str | None:
        """
        Look up customer ID by email address using Dodo Payments API.

        Args:
            email: Customer's email address

        Returns:
            str | None: Customer ID if found, None otherwise

        """
        customer_id = None
        try:
            response = requests.get(
                f"{DODO_API_BASE_URL}/customers",
                headers={"Authorization": f"Bearer {DODO_API_KEY}", "Content-Type": "application/json"},
                params={"email": email},
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == HTTP_OK:
                data = response.json()
                customers = data.get("items", [])

                if customers:
                    customer = customers[0]  # Take the first matching customer
                    customer_id = customer.get("customer_id")
                    logger.debug(f"Found customer {customer_id} for email {email}")
                else:
                    logger.debug(f"No customers found for email {email}")
            else:
                logger.error(f"Dodo Payments API error for customer lookup: {response.status_code} - {response.text}")

        except requests.Timeout:
            logger.error(f"Timeout while looking up customer for email {email}")
        except Exception as e:
            logger.error(f"Error looking up customer for email {email}: {e}")

        return customer_id

    def _get_latest_active_subscription(self, customer_id: str) -> dict[str, Any] | None:
        """
        Get the latest active subscription for a customer.

        Args:
            customer_id: Customer's ID from Dodo Payments

        Returns:
            dict | None: Latest active subscription data if found, None otherwise

        """
        latest_subscription = None
        try:
            response = requests.get(
                f"{DODO_API_BASE_URL}/subscriptions",
                headers={"Authorization": f"Bearer {DODO_API_KEY}", "Content-Type": "application/json"},
                params={"customer_id": customer_id, "status": "active"},
                timeout=REQUEST_TIMEOUT,
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
                else:
                    logger.debug(f"No active subscriptions found for customer {customer_id}")
            else:
                logger.error(
                    f"Dodo Payments API error for subscription lookup: {response.status_code} - {response.text}"
                )

        except requests.Timeout:
            logger.error(f"Timeout while looking up subscriptions for customer {customer_id}")
        except Exception as e:
            logger.error(f"Error looking up subscriptions for customer {customer_id}: {e}")

        return latest_subscription

    def _create_customer_portal_session(self, customer_id: str) -> str | None:
        """
        Create a customer portal session using Dodo Payments API.

        Args:
            customer_id: Customer's ID from Dodo Payments

        Returns:
            str | None: Portal URL if successful, None otherwise

        """
        portal_url = None
        try:
            response = requests.post(
                f"{DODO_API_BASE_URL}/customers/{customer_id}/customer-portal/session",
                headers={"Authorization": f"Bearer {DODO_API_KEY}", "Content-Type": "application/json"},
                timeout=REQUEST_TIMEOUT,
            )

            if response.status_code == HTTP_OK:
                data = response.json()
                portal_url = data.get("link")

                if portal_url:
                    logger.debug(f"Portal session created for customer {customer_id}")
                else:
                    logger.error(f"Portal URL not found in response for customer {customer_id}")
            else:
                logger.error(
                    f"Dodo Payments API error creating portal session: {response.status_code} - {response.text}"
                )

        except requests.Timeout:
            logger.error(f"Timeout while creating portal session for customer {customer_id}")
        except Exception as e:
            logger.error(f"Error creating portal session for customer {customer_id}: {e}")

        return portal_url
