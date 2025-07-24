"""
Tests for JWT authentication functionality.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import HTTPException, Request

from mxgo.auth import (
    AuthInfo,
    extract_jwt_from_request,
    get_current_user,
    get_current_user_with_plan,
    validate_jwt_token,
)
from mxgo.schemas import UserPlan


class TestJWTAuthentication:
    """Test cases for JWT authentication functions."""

    @pytest.fixture
    def jwt_secret(self):
        """Mock JWT secret for testing."""
        return "test_jwt_secret_key_for_testing_purposes_only"

    @pytest.fixture
    def valid_jwt_payload(self):
        """Valid JWT payload for testing."""
        return {
            "sub": "user_123",
            "email": "test@example.com",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
        }

    @pytest.fixture
    def expired_jwt_payload(self):
        """Expired JWT payload for testing."""
        return {
            "sub": "user_123",
            "email": "test@example.com",
            "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
            "iat": int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()),
        }

    @pytest.fixture
    def mock_request_with_valid_token(self, jwt_secret, valid_jwt_payload):
        """Mock request with valid JWT token."""
        token = jwt.encode(valid_jwt_payload, jwt_secret, algorithm="HS256")
        request = AsyncMock(spec=Request)
        request.headers = {"Authorization": f"Bearer {token}"}
        return request

    @pytest.fixture
    def mock_request_with_expired_token(self, jwt_secret, expired_jwt_payload):
        """Mock request with expired JWT token."""
        token = jwt.encode(expired_jwt_payload, jwt_secret, algorithm="HS256")
        request = AsyncMock(spec=Request)
        request.headers = {"Authorization": f"Bearer {token}"}
        return request

    @pytest.fixture
    def mock_request_no_auth_header(self):
        """Mock request without Authorization header."""
        request = AsyncMock(spec=Request)
        request.headers = {}
        return request

    @pytest.fixture
    def mock_request_malformed_auth_header(self):
        """Mock request with malformed Authorization header."""
        request = AsyncMock(spec=Request)
        request.headers = {"Authorization": "InvalidFormat token"}
        return request

    def test_validate_jwt_token_valid(self, jwt_secret, valid_jwt_payload):
        """Test validate_jwt_token with valid token."""
        with patch("mxgo.auth.JWT_SECRET", jwt_secret):
            token = jwt.encode(valid_jwt_payload, jwt_secret, algorithm="HS256")

            auth_info = validate_jwt_token(token)

            assert auth_info.is_authenticated is True
            assert auth_info.user_id == "user_123"
            assert auth_info.email == "test@example.com"
            assert isinstance(auth_info.expires_at, datetime)

    def test_validate_jwt_token_no_secret(self, jwt_secret, valid_jwt_payload):
        """Test validate_jwt_token raises error when JWT_SECRET is not configured."""
        with patch.dict(os.environ, {}, clear=True):
            token = jwt.encode(valid_jwt_payload, jwt_secret, algorithm="HS256")

            with pytest.raises(HTTPException) as exc_info:
                validate_jwt_token(token)

            assert exc_info.value.status_code == 500
            assert "Server configuration error" in exc_info.value.detail

    def test_validate_jwt_token_expired(self, jwt_secret, expired_jwt_payload):
        """Test validate_jwt_token raises error for expired token."""
        with patch("mxgo.auth.JWT_SECRET", jwt_secret):
            token = jwt.encode(expired_jwt_payload, jwt_secret, algorithm="HS256")

            with pytest.raises(HTTPException) as exc_info:
                validate_jwt_token(token)

            assert exc_info.value.status_code == 401
            assert "Token has expired" in exc_info.value.detail

    def test_validate_jwt_token_invalid_signature(self, jwt_secret, valid_jwt_payload):
        """Test validate_jwt_token raises error for invalid signature."""
        with patch("mxgo.auth.JWT_SECRET", jwt_secret):
            # Create token with different secret
            token = jwt.encode(valid_jwt_payload, "wrong_secret", algorithm="HS256")

            with pytest.raises(HTTPException) as exc_info:
                validate_jwt_token(token)

            assert exc_info.value.status_code == 401
            assert "Invalid token" in exc_info.value.detail

    def test_validate_jwt_token_malformed(self, jwt_secret):
        """Test validate_jwt_token raises error for malformed token."""
        with patch("mxgo.auth.JWT_SECRET", jwt_secret):
            with pytest.raises(HTTPException) as exc_info:
                validate_jwt_token("invalid.token.format")

            assert exc_info.value.status_code == 401
            assert "Invalid token" in exc_info.value.detail

    def test_validate_jwt_token_missing_sub(self, jwt_secret):
        """Test validate_jwt_token raises error when 'sub' field is missing."""
        payload = {
            "email": "test@example.com",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }

        with patch("mxgo.auth.JWT_SECRET", jwt_secret):
            token = jwt.encode(payload, jwt_secret, algorithm="HS256")

            with pytest.raises(HTTPException) as exc_info:
                validate_jwt_token(token)

            assert exc_info.value.status_code == 401
            assert "missing user ID" in exc_info.value.detail

    def test_validate_jwt_token_missing_email(self, jwt_secret):
        """Test validate_jwt_token raises error when 'email' field is missing."""
        payload = {
            "sub": "user_123",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        }

        with patch("mxgo.auth.JWT_SECRET", jwt_secret):
            token = jwt.encode(payload, jwt_secret, algorithm="HS256")

            with pytest.raises(HTTPException) as exc_info:
                validate_jwt_token(token)

            assert exc_info.value.status_code == 401
            assert "missing email" in exc_info.value.detail

    def test_validate_jwt_token_missing_exp(self, jwt_secret):
        """Test validate_jwt_token raises error when 'exp' field is missing."""
        payload = {
            "sub": "user_123",
            "email": "test@example.com",
        }

        with patch("mxgo.auth.JWT_SECRET", jwt_secret):
            token = jwt.encode(payload, jwt_secret, algorithm="HS256")

            with pytest.raises(HTTPException) as exc_info:
                validate_jwt_token(token)

            assert exc_info.value.status_code == 401
            assert "missing expiration" in exc_info.value.detail

    def test_extract_jwt_from_request_valid(self, mock_request_with_valid_token, jwt_secret, valid_jwt_payload):
        """Test extract_jwt_from_request with valid Authorization header."""
        expected_token = jwt.encode(valid_jwt_payload, jwt_secret, algorithm="HS256")

        token = extract_jwt_from_request(mock_request_with_valid_token)

        assert token == expected_token

    def test_extract_jwt_from_request_missing_header(self, mock_request_no_auth_header):
        """Test extract_jwt_from_request raises error when Authorization header is missing."""
        with pytest.raises(HTTPException) as exc_info:
            extract_jwt_from_request(mock_request_no_auth_header)

        assert exc_info.value.status_code == 401
        assert "Missing Authorization header" in exc_info.value.detail

    def test_extract_jwt_from_request_malformed_header(self, mock_request_malformed_auth_header):
        """Test extract_jwt_from_request raises error for malformed Authorization header."""
        with pytest.raises(HTTPException) as exc_info:
            extract_jwt_from_request(mock_request_malformed_auth_header)

        assert exc_info.value.status_code == 401
        assert "Invalid Authorization header format" in exc_info.value.detail

    def test_extract_jwt_from_request_empty_token(self):
        """Test extract_jwt_from_request raises error for empty token."""
        request = AsyncMock(spec=Request)
        request.headers = {"Authorization": "Bearer "}

        with pytest.raises(HTTPException) as exc_info:
            extract_jwt_from_request(request)

        assert exc_info.value.status_code == 401
        assert "Empty token" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_valid(self, mock_request_with_valid_token, jwt_secret):
        """Test get_current_user with valid JWT token."""
        with patch("mxgo.auth.JWT_SECRET", jwt_secret):
            auth_info = await get_current_user(mock_request_with_valid_token)

            assert auth_info.is_authenticated is True
            assert auth_info.user_id == "user_123"
            assert auth_info.email == "test@example.com"

    @pytest.mark.asyncio
    async def test_get_current_user_expired_token(self, mock_request_with_expired_token, jwt_secret):
        """Test get_current_user raises error for expired token."""
        with patch("mxgo.auth.JWT_SECRET", jwt_secret):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_request_with_expired_token)

            assert exc_info.value.status_code == 401
            assert "Token has expired" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_no_auth_header(self, mock_request_no_auth_header, jwt_secret):
        """Test get_current_user raises error when Authorization header is missing."""
        with patch.dict(os.environ, {"JWT_SECRET": jwt_secret}):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(mock_request_no_auth_header)

            assert exc_info.value.status_code == 401
            assert "Missing Authorization header" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_current_user_with_plan_valid(self, mock_request_with_valid_token, jwt_secret):
        """Test get_current_user_with_plan with valid token and successful plan lookup."""
        with (
            patch("mxgo.auth.JWT_SECRET", jwt_secret),
            patch("mxgo.user.get_user_plan", return_value=UserPlan.PRO) as mock_get_plan,
        ):
            auth_info = await get_current_user_with_plan(mock_request_with_valid_token)

            assert auth_info.is_authenticated is True
            assert auth_info.user_id == "user_123"
            assert auth_info.email == "test@example.com"
            assert auth_info.user_plan == UserPlan.PRO

            mock_get_plan.assert_called_once_with("test@example.com")

    @pytest.mark.asyncio
    async def test_get_current_user_with_plan_plan_lookup_fails(self, mock_request_with_valid_token, jwt_secret):
        """Test get_current_user_with_plan falls back to BETA when plan lookup fails."""
        with (
            patch("mxgo.auth.JWT_SECRET", jwt_secret),
            patch("mxgo.user.get_user_plan", side_effect=Exception("Plan lookup failed")),
        ):
            auth_info = await get_current_user_with_plan(mock_request_with_valid_token)

            assert auth_info.is_authenticated is True
            assert auth_info.user_id == "user_123"
            assert auth_info.email == "test@example.com"
            assert auth_info.user_plan == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_current_user_with_plan_invalid_token(self, mock_request_with_expired_token, jwt_secret):
        """Test get_current_user_with_plan raises error for invalid token."""
        with patch("mxgo.auth.JWT_SECRET", jwt_secret):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_with_plan(mock_request_with_expired_token)

            assert exc_info.value.status_code == 401
            assert "Token has expired" in exc_info.value.detail


class TestAuthInfo:
    """Test cases for AuthInfo model."""

    def test_auth_info_creation(self):
        """Test AuthInfo model creation with required fields."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        auth_info = AuthInfo(is_authenticated=True, user_id="user_123", email="test@example.com", expires_at=expires_at)

        assert auth_info.is_authenticated is True
        assert auth_info.user_id == "user_123"
        assert auth_info.email == "test@example.com"
        assert auth_info.expires_at == expires_at
        assert auth_info.user_plan is None

    def test_auth_info_with_user_plan(self):
        """Test AuthInfo model creation with user plan."""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        auth_info = AuthInfo(
            is_authenticated=True,
            user_id="user_123",
            email="test@example.com",
            expires_at=expires_at,
            user_plan=UserPlan.PRO,
        )

        assert auth_info.user_plan == UserPlan.PRO
