"""
JWT authentication middleware and utilities.

This module provides JWT token validation and authentication functionality
for protected API endpoints.
"""

import os
from datetime import datetime, timezone

import jwt
from fastapi import HTTPException, Request, status
from pydantic import BaseModel

from mxgo import user
from mxgo._logging import get_logger
from mxgo.schemas import UserPlan

# Configure logging
logger = get_logger(__name__)

# JWT configuration
JWT_SECRET = os.getenv("JWT_SECRET")
JWT_ALGORITHM = "HS256"


class AuthInfo(BaseModel):
    """Authentication information extracted from JWT token."""

    is_authenticated: bool
    user_id: str
    email: str
    expires_at: datetime
    user_plan: UserPlan | None = None


def validate_jwt_token(token: str) -> AuthInfo:
    """
    Validate JWT token and extract user information.

    Args:
        token: JWT token string

    Returns:
        AuthInfo: Validated authentication information

    Raises:
        HTTPException: If token is invalid, expired, or malformed

    """
    if not JWT_SECRET:
        logger.error("JWT_SECRET not configured")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server configuration error")

    try:
        # Decode and validate the JWT token
        payload = jwt.decode(
            token, JWT_SECRET, algorithms=[JWT_ALGORITHM], options={"verify_exp": True}, audience="authenticated"
        )

        # Extract required fields
        user_id = payload.get("sub")
        email = payload.get("email")
        exp = payload.get("exp")

        if not user_id:
            logger.warning("JWT token missing 'sub' (user_id) field")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing user ID")

        if not email:
            logger.warning("JWT token missing 'email' field")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing email")

        if not exp:
            logger.warning("JWT token missing 'exp' (expiration) field")
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token: missing expiration")

        # Convert expiration timestamp to datetime
        expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)

        # Create auth info
        auth_info = AuthInfo(is_authenticated=True, user_id=user_id, email=email, expires_at=expires_at)

        logger.info(f"Successfully validated JWT token for user {email}")

    except jwt.ExpiredSignatureError as e:
        logger.warning("JWT token has expired")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired") from e
    except jwt.InvalidTokenError as e:
        logger.warning(f"Invalid JWT token: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e
    except HTTPException:
        # Re-raise HTTP exceptions as-is (for missing fields)
        raise
    except Exception as e:
        logger.error(f"Error validating JWT token: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token validation failed") from e
    else:
        return auth_info


def extract_jwt_from_request(request: Request) -> str:
    """
    Extract JWT token from request Authorization header.

    Args:
        request: FastAPI request object

    Returns:
        str: JWT token string

    Raises:
        HTTPException: If Authorization header is missing or malformed

    """
    auth_header = request.headers.get("Authorization")

    if not auth_header:
        logger.warning("Missing Authorization header")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization header")

    # Check for Bearer token format
    if not auth_header.startswith("Bearer "):
        logger.warning("Authorization header does not start with 'Bearer '")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Authorization header format")

    # Extract token
    token = auth_header[7:]  # Remove "Bearer " prefix

    if not token:
        logger.warning("Empty token in Authorization header")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Empty token")

    return token


async def get_current_user(request: Request) -> AuthInfo:
    """
    FastAPI dependency to get current authenticated user from JWT token.

    Args:
        request: FastAPI request object

    Returns:
        AuthInfo: Current user authentication information

    Raises:
        HTTPException: If authentication fails

    """
    try:
        # Extract JWT token from request
        token = extract_jwt_from_request(request)

        # Validate token and get user info
        return validate_jwt_token(token)

    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        logger.error(f"Unexpected error in JWT authentication: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication failed") from e


async def get_current_user_with_plan(request: Request) -> AuthInfo:
    """
    FastAPI dependency to get current authenticated user with user plan information.

    Args:
        request: FastAPI request object

    Returns:
        AuthInfo: Current user authentication information with user plan

    Raises:
        HTTPException: If authentication fails

    """
    # Get basic auth info
    auth_info = await get_current_user(request)

    try:
        # Get user plan
        user_plan = await user.get_user_plan(auth_info.email)
        auth_info.user_plan = user_plan

        logger.info(f"User {auth_info.email} has plan: {user_plan}")

    except Exception as e:
        logger.warning(f"Could not determine user plan for {auth_info.email}: {e}")
        # Don't fail authentication if we can't get the plan
        auth_info.user_plan = UserPlan.BETA

    return auth_info
