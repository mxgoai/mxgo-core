#!/usr/bin/env python3
"""
Generate a test JWT token for testing the /suggestions endpoint.
"""

import os
from datetime import datetime, timedelta, timezone

import jwt
from dotenv import load_dotenv

load_dotenv()

# JWT configuration
JWT_ALGORITHM = "HS256"


def generate_test_jwt(email: str = "test@example.com", user_id: str = "test_user_123") -> str:
    """Generate a test JWT token."""
    # Get JWT secret at runtime (not import time)
    jwt_secret = os.environ["JWT_SECRET"]

    # Token expires in 1 hour
    exp = datetime.now(timezone.utc) + timedelta(hours=1)

    payload = {
        "sub": user_id,  # Subject (user ID)
        "email": email,
        "exp": int(exp.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),  # Issued at
        "aud": "authenticated",  # Audience
    }

    return jwt.encode(payload, jwt_secret, algorithm=JWT_ALGORITHM)


if __name__ == "__main__":
    token = generate_test_jwt(email="satwikkansal@gmail.com")
