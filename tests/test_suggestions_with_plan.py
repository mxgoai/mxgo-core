#!/usr/bin/env python3
"""
Test script for the /suggestions API endpoint with actual PRO user plan.
"""

import os

import requests

from tests.generate_test_jwt import generate_test_jwt

# HTTP status codes
HTTP_OK = 200

# Set environment variables for testing
os.environ["JWT_SECRET"] = "test_secret_key_for_development_only"  # noqa: S105
os.environ["SUGGESTIONS_API_KEY"] = "hellobello"


def test_suggestions_with_pro_plan():
    """Test the /suggestions API endpoint with a PRO user."""
    email = "satwikkansal@gmail.com"
    plan_type = "PRO"

    # Generate test JWT token for the specific email
    jwt_token = generate_test_jwt(email, f"user_{email.replace('@', '_').replace('.', '_')}")

    # API endpoint
    url = "http://127.0.0.1:9192/suggestions"

    # Headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {jwt_token}",
        "x-suggestions-api-key": "hellobello",
    }

    # Request payload - using the same email in user_email_id
    payload = [
        {
            "email_identified": f"test-email-{email.replace('@', '-').replace('.', '-')}",
            "user_email_id": email,
            "sender_email": "sender@example.com",
            "cc_emails": ["cc@example.com"],
            "Subject": f"Test Email Subject from {plan_type} user",
            "email_content": f"This is a test email content for suggestions API from a {plan_type} user.",
            "attachments": [],
        }
    ]

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code == HTTP_OK:
            response.json()
        else:
            pass

    except requests.exceptions.RequestException:
        pass


def test_suggestions_with_beta_plan():
    """Test the /suggestions API endpoint with a BETA user."""
    email = "test@example.com"
    plan_type = "BETA"

    # Generate test JWT token for the specific email
    jwt_token = generate_test_jwt(email, f"user_{email.replace('@', '_').replace('.', '_')}")

    # API endpoint
    url = "http://127.0.0.1:9192/suggestions"

    # Headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {jwt_token}",
        "x-suggestions-api-key": "hellobello",
    }

    # Request payload - using the same email in user_email_id
    payload = [
        {
            "email_identified": f"test-email-{email.replace('@', '-').replace('.', '-')}",
            "user_email_id": email,
            "sender_email": "sender@example.com",
            "cc_emails": ["cc@example.com"],
            "Subject": f"Test Email Subject from {plan_type} user",
            "email_content": f"This is a test email content for suggestions API from a {plan_type} user.",
            "attachments": [],
        }
    ]

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code == HTTP_OK:
            response.json()
        else:
            pass

    except requests.exceptions.RequestException:
        pass


def main():
    """Test both PRO and BETA users."""
    # Test PRO user
    test_suggestions_with_pro_plan()

    # Test BETA user
    test_suggestions_with_beta_plan()


if __name__ == "__main__":
    main()
