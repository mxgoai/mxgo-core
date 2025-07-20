#!/usr/bin/env python3
"""
Test script for the /suggestions API endpoint.
"""

import os

import requests

from tests.generate_test_jwt import generate_test_jwt

# HTTP status codes
HTTP_OK = 200

# Set environment variables for testing
os.environ["JWT_SECRET"] = "test_secret_key_for_development_only"  # noqa: S105
os.environ["SUGGESTIONS_API_KEY"] = "test-suggestions-key"


def test_suggestions_api():
    """Test the /suggestions API endpoint."""
    # Generate test JWT token
    jwt_token = generate_test_jwt("test@example.com", "test_user_123")

    # API endpoint
    url = "http://127.0.0.1:9192/suggestions"

    # Headers
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {jwt_token}",
        "x-suggestions-api-key": "hellobello",
    }

    # Request payload
    payload = [
        {
            "email_identified": "test-email-123",
            "user_email_id": "test@example.com",
            "sender_email": "sender@example.com",
            "cc_emails": ["cc@example.com"],
            "Subject": "Test Email Subject",
            "email_content": "This is a test email content for suggestions API.",
            "attachments": [],
        }
    ]

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if response.status_code == HTTP_OK:
            pass
        else:
            pass

    except requests.exceptions.RequestException:
        pass


if __name__ == "__main__":
    test_suggestions_api()
