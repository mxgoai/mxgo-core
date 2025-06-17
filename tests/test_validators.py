from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fakeredis.aioredis import FakeRedis
from starlette.responses import Response

from mxtoai.schemas import RateLimitPlan
from mxtoai.validators import (
    check_rate_limit_redis,
    get_current_timestamp_for_period,
    get_domain_from_email,
    normalize_email,
    send_rate_limit_rejection_email,
    validate_attachments,
    validate_email_handle,
    validate_email_whitelist,
    validate_rate_limits,
)


class TestEmailNormalization:
    """Test email normalization functions."""

    def test_normalize_email_basic(self):
        """Test basic email normalization."""
        result = normalize_email("test@example.com")
        assert result == "test@example.com"

    def test_normalize_email_with_alias(self):
        """Test email normalization with +alias."""
        result = normalize_email("test+alias@example.com")
        assert result == "test@example.com"

    def test_normalize_email_complex_alias(self):
        """Test email normalization with complex alias."""
        result = normalize_email("user+important.info@EXAMPLE.COM")
        assert result == "user@example.com"

    def test_normalize_email_invalid(self):
        """Test email normalization with invalid email."""
        result = normalize_email("invalid-email")
        assert result == "invalid-email"

    def test_get_domain_from_email(self):
        """Test domain extraction from valid email."""
        result = get_domain_from_email("test@example.com")
        assert result == "example.com"

    def test_get_domain_from_email_invalid(self):
        """Test domain extraction from invalid email."""
        result = get_domain_from_email("invalid-email")
        assert result == ""


class TestRateLimiting:
    """Test rate limiting functionality."""

    def test_get_current_timestamp_for_period_hour(self):
        """Test timestamp generation for hourly periods."""
        dt = datetime(2024, 1, 15, 14, 30, 45, tzinfo=timezone.utc)
        result = get_current_timestamp_for_period("hour", dt)
        assert result == "2024011514"  # Format: YYYYMMDDHH

    def test_get_current_timestamp_for_period_day(self):
        """Test timestamp generation for daily periods."""
        dt = datetime(2024, 1, 15, 14, 30, 45, tzinfo=timezone.utc)
        result = get_current_timestamp_for_period("day", dt)
        assert result == "20240115"  # Format: YYYYMMDD

    def test_get_current_timestamp_for_period_month(self):
        """Test timestamp generation for monthly periods."""
        dt = datetime(2024, 1, 15, 14, 30, 45, tzinfo=timezone.utc)
        result = get_current_timestamp_for_period("month", dt)
        assert result == "202401"  # Format: YYYYMM

    def test_get_current_timestamp_for_period_invalid(self):
        """Test timestamp generation for invalid period."""
        dt = datetime(2024, 1, 15, 14, 30, 45, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="Unknown period name"):
            get_current_timestamp_for_period("invalid", dt)

    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_within_limits(self):
        """Test rate limit check when within limits."""
        fake_redis = FakeRedis()

        with patch("mxtoai.validators.redis_client", fake_redis):
            result = await check_rate_limit_redis(
                key_type="email",
                identifier="test@example.com",
                plan_or_domain_limits={"hour": {"limit": 10}},
                current_dt=datetime.now(timezone.utc),
                plan_name_for_key="beta"
            )

        assert result is None  # Within limits

    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_exceeds_limits(self):
        """Test rate limit check when exceeding limits."""
        fake_redis = FakeRedis()

        # Pre-populate Redis to simulate exceeded limits
        # Key format: rate_limit:email:identifier:plan:period:timestamp
        key = "rate_limit:email:test@example.com:beta:hour:2024011514"
        await fake_redis.setex(key, 3600, "15")  # Set count above limit

        with patch("mxtoai.validators.redis_client", fake_redis):
            result = await check_rate_limit_redis(
                key_type="email",
                identifier="test@example.com",
                plan_or_domain_limits={"hour": {"limit": 10}},
                current_dt=datetime(2024, 1, 15, 14, 30, 45, tzinfo=timezone.utc),
                plan_name_for_key="beta"
            )

        assert result == "hour"  # Exceeded hourly limit

    @pytest.mark.asyncio
    async def test_check_rate_limit_redis_no_client(self):
        """Test rate limit check with no Redis client."""
        with patch("mxtoai.validators.redis_client", None):
            result = await check_rate_limit_redis(
                key_type="email",
                identifier="test@example.com",
                plan_or_domain_limits={"hour": {"limit": 10}},
                current_dt=datetime.now(timezone.utc),
                plan_name_for_key="beta"
            )

        assert result is None  # No Redis, no rate limiting

    @pytest.mark.asyncio
    async def test_send_rate_limit_rejection_email(self):
        """Test sending rate limit rejection email."""
        with patch("mxtoai.validators.send_email_reply", new_callable=AsyncMock) as mock_send:
            await send_rate_limit_rejection_email(
                from_email="user@example.com",
                to="ask@mxtoai.com",
                subject="Test Subject",
                messageId="test-message-id",
                limit_type="email hour"
            )

            mock_send.assert_called_once()
            call_args = mock_send.call_args[0]
            assert call_args[0]["from"] == "user@example.com"
            assert "limit has been exceeded" in call_args[1]

    @pytest.mark.asyncio
    async def test_validate_rate_limits_within_limits(self):
        """Test rate limit validation when within limits."""
        fake_redis = FakeRedis()

        with patch("mxtoai.validators.redis_client", fake_redis):
            result = await validate_rate_limits(
                from_email="test@example.com",
                to="ask@mxtoai.com",
                subject="Test Subject",
                messageId="test-message-id",
                plan=RateLimitPlan.BETA
            )

        assert result is None  # Within limits

    @pytest.mark.asyncio
    async def test_validate_rate_limits_no_redis_client(self):
        """Test rate limit validation with no Redis client."""
        with patch("mxtoai.validators.redis_client", None):
            result = await validate_rate_limits(
                from_email="test@example.com",
                to="ask@mxtoai.com",
                subject="Test Subject",
                messageId="test-message-id",
                plan=RateLimitPlan.BETA
            )

        assert result is None  # No Redis, no rate limiting


class TestValidationFunctions:
    """Test main validation functions."""

    @pytest.mark.asyncio
    async def test_validate_email_whitelist_whitelisted(self):
        """Test email whitelist validation for whitelisted email."""
        with patch("mxtoai.validators.is_email_whitelisted", return_value=(True, True)):
            result = await validate_email_whitelist(
                from_email="whitelisted@example.com",
                to="ask@mxtoai.com",
                subject="Test Subject",
                messageId="test-message-id"
            )

        assert result is None  # Whitelisted emails should pass

    @pytest.mark.asyncio
    async def test_validate_email_whitelist_not_whitelisted(self):
        """Test email whitelist validation for non-whitelisted email."""
        with patch("mxtoai.validators.is_email_whitelisted", return_value=(False, False)), \
             patch("mxtoai.validators.get_whitelist_signup_url", return_value="https://signup.url"), \
             patch("mxtoai.validators.trigger_automatic_verification", return_value=True), \
             patch("mxtoai.validators.send_email_reply", new_callable=AsyncMock) as mock_send:

            result = await validate_email_whitelist(
                from_email="notlisted@example.com",
                to="ask@mxtoai.com",
                subject="Test Subject",
                messageId="test-message-id"
            )

            assert isinstance(result, Response)
            assert result.status_code == 403
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_email_handle_valid_handle(self):
        """Test email handle validation for valid handle."""
        with patch("mxtoai.validators.processing_instructions_resolver") as mock_resolver:
            mock_resolver.return_value = "some_instructions"

            result, handle = await validate_email_handle(
                to="ask@mxtoai.com",
                from_email="user@example.com",
                subject="Test Subject",
                messageId="test-message-id"
            )

            assert result is None
            assert handle == "ask"

    @pytest.mark.asyncio
    async def test_validate_email_handle_invalid_handle(self):
        """Test email handle validation for invalid handle."""
        from mxtoai import exceptions

        with patch("mxtoai.validators.processing_instructions_resolver") as mock_resolver, \
             patch("mxtoai.validators.send_email_reply", new_callable=AsyncMock) as mock_send:

            mock_resolver.side_effect = exceptions.UnspportedHandleException("Invalid handle")

            result, handle = await validate_email_handle(
                to="invalid@mxtoai.com",
                from_email="user@example.com",
                subject="Test Subject",
                messageId="test-message-id"
            )

            assert isinstance(result, Response)
            assert result.status_code == 400
            assert handle is None
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_attachments_valid(self):
        """Test attachment validation for valid attachments."""
        attachments = [
            {
                "filename": "small.txt",
                "content": "dGVzdA==",  # base64 encoded "test"
                "contentType": "text/plain",
                "size": 4
            }
        ]

        result = await validate_attachments(
            attachments=attachments,
            from_email="user@example.com",
            to="ask@mxtoai.com",
            subject="Test Subject",
            messageId="test-message-id"
        )

        assert result is None  # Valid attachments should pass

    @pytest.mark.asyncio
    async def test_validate_attachments_too_large(self):
        """Test attachment validation for oversized attachments."""
        # Create a large attachment (simulate 20MB)
        attachments = [
            {
                "filename": "large.txt",
                "content": "dGVzdA==",  # base64 encoded "test"
                "contentType": "text/plain",
                "size": 20 * 1024 * 1024  # 20MB
            }
        ]

        with patch("mxtoai.validators.send_email_reply", new_callable=AsyncMock) as mock_send:
            result = await validate_attachments(
                attachments=attachments,
                from_email="user@example.com",
                to="ask@mxtoai.com",
                subject="Test Subject",
                messageId="test-message-id"
            )

            assert isinstance(result, Response)
            assert result.status_code == 400  # The actual function returns 400, not 413
            mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_attachments_too_many(self):
        """Test attachment validation for too many attachments."""
        # Create 10 attachments (exceeds MAX_ATTACHMENTS_COUNT of 5)
        attachments = []
        for i in range(10):
            attachments.append({
                "filename": f"test{i}.txt",
                "content": "dGVzdA==",  # base64 encoded "test"
                "contentType": "text/plain",
                "size": 4
            })

        with patch("mxtoai.validators.send_email_reply", new_callable=AsyncMock) as mock_send:
            result = await validate_attachments(
                attachments=attachments,
                from_email="user@example.com",
                to="ask@mxtoai.com",
                subject="Test Subject",
                messageId="test-message-id"
            )

            assert isinstance(result, Response)
            assert result.status_code == 400  # The function returns 400 for all validation failures
            mock_send.assert_called_once()
