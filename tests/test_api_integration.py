"""
Integration tests for API endpoints with Dodo Payments and JWT authentication.
"""

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi.testclient import TestClient

from mxtoai.api import app
from mxtoai.schemas import UserPlan


class TestProcessEmailIntegration:
    """Integration tests for /process-email endpoint with user plan integration."""

    @pytest.fixture
    def client(self):
        """Test client for API testing."""
        return TestClient(app)

    @pytest.fixture
    def mock_env_vars(self):
        """Mock environment variables for testing."""
        with patch.dict(
            os.environ,
            {
                "X_API_KEY": "test_api_key",
                "DODO_API_KEY": "test_dodo_key",
                "PRO_PLAN_PRODUCT_ID": "pro_product_123",
                "JWT_SECRET": "test_jwt_secret",
            },
        ):
            yield

    @pytest.fixture
    def mock_redis_client(self):
        """Mock Redis client for rate limiting."""
        with patch("mxtoai.validators.redis_client") as mock_redis:
            mock_redis.pipeline.return_value.__aenter__.return_value.execute.return_value = [1, True]
            yield mock_redis

    @pytest.fixture
    def mock_email_whitelist(self):
        """Mock email whitelist validation."""
        with patch("mxtoai.validators.is_email_whitelisted", return_value=(True, True)):
            yield

    @pytest.fixture
    def mock_email_sender(self):
        """Mock email sender to prevent actual email sending."""
        with patch("mxtoai.validators.send_email_reply"):
            yield

    @pytest.fixture
    def mock_task_queue(self):
        """Mock task queue to prevent actual task processing."""
        with patch("mxtoai.api.process_email_task"):
            yield

    def test_process_email_with_pro_user_plan(
        self, client, mock_env_vars, mock_redis_client, mock_email_whitelist, mock_email_sender, mock_task_queue
    ):
        """Test /process-email endpoint uses PRO user plan for rate limiting."""
        # Mock get_user_plan to return PRO
        with patch("user.get_user_plan", return_value=UserPlan.PRO) as mock_get_plan:
            response = client.post(
                "/process-email",
                data={
                    "from_email": "test@example.com",
                    "to": "ask@mxtoai.com",
                    "subject": "Test email",
                    "textContent": "Test content",
                },
                headers={"x-api-key": "test_api_key"},
            )

            assert response.status_code == 200
            mock_get_plan.assert_called_once_with("test@example.com")

    def test_process_email_with_beta_user_plan(
        self, client, mock_env_vars, mock_redis_client, mock_email_whitelist, mock_email_sender, mock_task_queue
    ):
        """Test /process-email endpoint uses BETA user plan for rate limiting."""
        # Mock get_user_plan to return BETA
        with patch("user.get_user_plan", return_value=UserPlan.BETA) as mock_get_plan:
            response = client.post(
                "/process-email",
                data={
                    "from_email": "test@example.com",
                    "to": "ask@mxtoai.com",
                    "subject": "Test email",
                    "textContent": "Test content",
                },
                headers={"x-api-key": "test_api_key"},
            )

            assert response.status_code == 200
            mock_get_plan.assert_called_once_with("test@example.com")

    def test_process_email_plan_lookup_failure_fallback(
        self, client, mock_env_vars, mock_redis_client, mock_email_whitelist, mock_email_sender, mock_task_queue
    ):
        """Test /process-email endpoint falls back to BETA when plan lookup fails."""
        # Mock get_user_plan to raise exception
        with (
            patch("user.get_user_plan", side_effect=Exception("Plan lookup failed")) as mock_get_plan,
            patch("mxtoai.validators.validate_rate_limits", return_value=None) as mock_rate_limits,
        ):
            response = client.post(
                "/process-email",
                data={
                    "from_email": "test@example.com",
                    "to": "ask@mxtoai.com",
                    "subject": "Test email",
                    "textContent": "Test content",
                },
                headers={"x-api-key": "test_api_key"},
            )

            assert response.status_code == 200
            mock_get_plan.assert_called_once_with("test@example.com")
            # Verify rate limits called with BETA plan as fallback
            mock_rate_limits.assert_called_once()
            call_args = mock_rate_limits.call_args
            assert call_args[1]["plan"] == UserPlan.BETA

    def test_process_email_invalid_api_key(self, client, mock_env_vars):
        """Test /process-email endpoint rejects invalid API key."""
        response = client.post(
            "/process-email",
            data={
                "from_email": "test@example.com",
                "to": "ask@mxtoai.com",
                "subject": "Test email",
                "textContent": "Test content",
            },
            headers={"x-api-key": "invalid_key"},
        )

        assert response.status_code == 401
        assert "Invalid API key" in response.json()["message"]

    def test_process_email_rate_limit_exceeded(self, client, mock_env_vars, mock_email_whitelist, mock_email_sender):
        """Test /process-email endpoint handles rate limit exceeded."""
        with (
            patch("user.get_user_plan", return_value=UserPlan.BETA),
            patch("mxtoai.validators.validate_rate_limits") as mock_rate_limits,
        ):
            # Mock rate limit exceeded response
            mock_response = AsyncMock()
            mock_response.status_code = 429
            mock_rate_limits.return_value = mock_response

            response = client.post(
                "/process-email",
                data={
                    "from_email": "test@example.com",
                    "to": "ask@mxtoai.com",
                    "subject": "Test email",
                    "textContent": "Test content",
                },
                headers={"x-api-key": "test_api_key"},
            )

            assert response.status_code == 429


class TestSuggestionsIntegration:
    """Integration tests for /suggestions endpoint with JWT authentication."""

    @pytest.fixture
    def client(self):
        """Test client for API testing."""
        return TestClient(app)

    @pytest.fixture
    def jwt_secret(self):
        """JWT secret for testing."""
        return "test_jwt_secret"

    @pytest.fixture
    def valid_jwt_token(self, jwt_secret):
        """Valid JWT token for testing."""
        payload = {
            "sub": "user_123",
            "email": "test@example.com",
            "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp()),
        }
        return jwt.encode(payload, jwt_secret, algorithm="HS256")

    @pytest.fixture
    def expired_jwt_token(self, jwt_secret):
        """Expired JWT token for testing."""
        payload = {
            "sub": "user_123",
            "email": "test@example.com",
            "exp": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp()),
            "iat": int((datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()),
        }
        return jwt.encode(payload, jwt_secret, algorithm="HS256")

    @pytest.fixture
    def mock_env_vars(self, jwt_secret):
        """Mock environment variables for testing."""
        with patch.dict(os.environ, {"SUGGESTIONS_API_KEY": "test_suggestions_key", "JWT_SECRET": jwt_secret}):
            yield

    @pytest.fixture
    def mock_email_whitelist(self):
        """Mock email whitelist validation."""
        with patch("mxtoai.validators.is_email_whitelisted", return_value=(True, True)):
            yield

    @pytest.fixture
    def mock_suggestions_model(self):
        """Mock suggestions model."""
        with patch("mxtoai.suggestions.get_suggestions_model"):
            yield

    @pytest.fixture
    def mock_generate_suggestions(self):
        """Mock generate_suggestions function."""
        with patch("mxtoai.suggestions.generate_suggestions") as mock_gen:
            mock_gen.return_value = AsyncMock()
            mock_gen.return_value.email_identified = "test_email_123"
            mock_gen.return_value.user_email_id = "test@example.com"
            mock_gen.return_value.suggestions = []
            yield mock_gen

    @pytest.fixture
    def sample_suggestion_request(self):
        """Sample suggestion request data."""
        return [
            {
                "email_identified": "test_email_123",
                "user_email_id": "test@example.com",
                "sender_email": "sender@example.com",
                "cc_emails": [],
                "Subject": "Test email",
                "email_content": "Test content",
                "attachments": [],
            }
        ]

    def test_suggestions_with_valid_jwt_and_api_key(
        self,
        client,
        mock_env_vars,
        valid_jwt_token,
        sample_suggestion_request,
        mock_email_whitelist,
        mock_suggestions_model,
        mock_generate_suggestions,
    ):
        """Test /suggestions endpoint with valid JWT token and API key."""
        response = client.post(
            "/suggestions",
            json=sample_suggestion_request,
            headers={"Authorization": f"Bearer {valid_jwt_token}", "x-suggestions-api-key": "test_suggestions_key"},
        )

        assert response.status_code == 200
        mock_generate_suggestions.assert_called_once()

    def test_suggestions_missing_jwt_token(self, client, mock_env_vars, sample_suggestion_request):
        """Test /suggestions endpoint rejects requests without JWT token."""
        response = client.post(
            "/suggestions", json=sample_suggestion_request, headers={"x-suggestions-api-key": "test_suggestions_key"}
        )

        assert response.status_code == 401
        assert "Missing Authorization header" in response.json()["detail"]

    def test_suggestions_expired_jwt_token(self, client, mock_env_vars, expired_jwt_token, sample_suggestion_request):
        """Test /suggestions endpoint rejects expired JWT tokens."""
        response = client.post(
            "/suggestions",
            json=sample_suggestion_request,
            headers={"Authorization": f"Bearer {expired_jwt_token}", "x-suggestions-api-key": "test_suggestions_key"},
        )

        assert response.status_code == 401
        assert "Token has expired" in response.json()["detail"]

    def test_suggestions_invalid_jwt_token(self, client, mock_env_vars, sample_suggestion_request):
        """Test /suggestions endpoint rejects invalid JWT tokens."""
        response = client.post(
            "/suggestions",
            json=sample_suggestion_request,
            headers={"Authorization": "Bearer invalid.jwt.token", "x-suggestions-api-key": "test_suggestions_key"},
        )

        assert response.status_code == 401
        assert "Invalid token" in response.json()["detail"]

    def test_suggestions_malformed_auth_header(self, client, mock_env_vars, sample_suggestion_request):
        """Test /suggestions endpoint rejects malformed Authorization header."""
        response = client.post(
            "/suggestions",
            json=sample_suggestion_request,
            headers={"Authorization": "InvalidFormat token", "x-suggestions-api-key": "test_suggestions_key"},
        )

        assert response.status_code == 401
        assert "Invalid Authorization header format" in response.json()["detail"]

    def test_suggestions_missing_api_key(self, client, mock_env_vars, valid_jwt_token, sample_suggestion_request):
        """Test /suggestions endpoint still requires API key alongside JWT."""
        response = client.post(
            "/suggestions", json=sample_suggestion_request, headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )

        assert response.status_code == 422
        assert "Missing required header: x-suggestions-api-key" in response.json()["detail"]

    def test_suggestions_invalid_api_key(self, client, mock_env_vars, valid_jwt_token, sample_suggestion_request):
        """Test /suggestions endpoint rejects invalid API key even with valid JWT."""
        response = client.post(
            "/suggestions",
            json=sample_suggestion_request,
            headers={"Authorization": f"Bearer {valid_jwt_token}", "x-suggestions-api-key": "invalid_key"},
        )

        assert response.status_code == 401
        assert "Invalid suggestions API key" in response.json()["message"]

    def test_suggestions_user_not_whitelisted(
        self, client, mock_env_vars, valid_jwt_token, sample_suggestion_request, mock_suggestions_model
    ):
        """Test /suggestions endpoint handles non-whitelisted users."""
        with patch("mxtoai.validators.is_email_whitelisted", return_value=(False, False)):
            response = client.post(
                "/suggestions",
                json=sample_suggestion_request,
                headers={"Authorization": f"Bearer {valid_jwt_token}", "x-suggestions-api-key": "test_suggestions_key"},
            )

            assert response.status_code == 403
            assert "Email verification required" in response.json()["detail"]


class TestBackwardCompatibility:
    """Tests to ensure backward compatibility with existing functionality."""

    @pytest.fixture
    def client(self):
        """Test client for API testing."""
        return TestClient(app)

    @pytest.fixture
    def mock_env_vars(self):
        """Mock environment variables for testing."""
        with patch.dict(
            os.environ,
            {
                "X_API_KEY": "test_api_key",
            },
        ):
            yield

    def test_process_email_without_dodo_integration(self, client, mock_env_vars):
        """Test /process-email endpoint works without Dodo Payments configuration."""
        with (
            patch("mxtoai.validators.redis_client", None),
            patch("mxtoai.validators.is_email_whitelisted", return_value=(True, True)),
            patch("mxtoai.validators.send_email_reply"),
            patch("mxtoai.api.process_email_task"),
            patch("user.get_user_plan", return_value=UserPlan.BETA),
        ):
            response = client.post(
                "/process-email",
                data={
                    "from_email": "test@example.com",
                    "to": "ask@mxtoai.com",
                    "subject": "Test email",
                    "textContent": "Test content",
                },
                headers={"x-api-key": "test_api_key"},
            )

            # Should still work, falling back to BETA plan
            assert response.status_code == 200

    def test_existing_api_key_validation_unchanged(self, client, mock_env_vars):
        """Test existing API key validation still works as before."""
        response = client.post(
            "/process-email",
            data={
                "from_email": "test@example.com",
                "to": "ask@mxtoai.com",
                "subject": "Test email",
                "textContent": "Test content",
            },
            headers={"x-api-key": "wrong_key"},
        )

        assert response.status_code == 401
        assert "Invalid API key" in response.json()["message"]

    def test_health_endpoint_unchanged(self, client):
        """Test health endpoint still works as before."""
        with patch("mxtoai.api.rabbitmq_broker"), patch("mxtoai.api.init_db_connection"):
            response = client.get("/health")
            assert response.status_code == 200
            assert "status" in response.json()
