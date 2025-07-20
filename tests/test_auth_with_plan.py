#!/usr/bin/env python3
"""
Test script to verify JWT authentication with user plan injection.
"""

import os

from dotenv import load_dotenv

# Load environment variables FIRST
load_dotenv()

# Set JWT secret for testing
os.environ["JWT_SECRET"] = "test_secret_key_for_development_only"  # noqa: S105

import asyncio
import traceback
from unittest.mock import Mock

from fastapi import Request

from mxtoai.auth import get_current_user, get_current_user_with_plan
from mxtoai.schemas import UserPlan
from tests.generate_test_jwt import generate_test_jwt


async def test_auth_with_plan():
    """Test JWT authentication with user plan determination."""
    # Test emails
    test_cases = [("satwikkansal@gmail.com", "PRO user"), ("test@example.com", "BETA user")]

    for email, _description in test_cases:
        # Generate JWT token
        jwt_token = generate_test_jwt(email, f"user_{email.replace('@', '_').replace('.', '_')}")

        # Mock request object
        mock_request = Mock(spec=Request)
        mock_request.headers = {"Authorization": f"Bearer {jwt_token}"}

        try:
            # Test basic authentication
            await get_current_user(mock_request)

            # Test authentication with plan
            auth_with_plan = await get_current_user_with_plan(mock_request)

            if auth_with_plan.user_plan in (UserPlan.PRO, UserPlan.BETA):
                pass
            else:
                pass

        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    # Run the test
    asyncio.run(test_auth_with_plan())
