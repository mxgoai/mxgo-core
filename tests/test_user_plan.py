"""
Tests for user plan management and Dodo Payments integration.

This module tests the get_user_plan function and related Dodo Payments API integration.
"""

import os
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import user

from mxtoai.schemas import UserPlan


class TestGetUserPlan:
    """Test cases for get_user_plan function."""

    @pytest.fixture
    def mock_env_vars(self):
        """Mock environment variables for testing."""
        with patch.dict(os.environ, {"DODO_API_KEY": "test_dodo_key", "PRO_PLAN_PRODUCT_ID": "pro_product_123"}):
            yield

    @pytest.fixture
    def mock_customer_response(self):
        """Mock successful customer lookup response."""
        return {
            "items": [
                {
                    "business_id": "business_123",
                    "created_at": "2023-11-07T05:31:56Z",
                    "customer_id": "customer_456",
                    "email": "test@example.com",
                    "name": "Test User",
                    "phone_number": "+1234567890",
                }
            ]
        }

    @pytest.fixture
    def mock_subscription_response(self):
        """Mock successful subscription lookup response for PRO plan."""
        return {
            "items": [
                {
                    "subscription_id": "sub_789",
                    "customer_id": "customer_456",
                    "product_id": "pro_product_123",
                    "status": "active",
                    "created_at": "2023-11-07T05:31:56Z",
                    "currency": "USD",
                    "recurring_pre_tax_amount": 29.99,
                }
            ]
        }

    @pytest.fixture
    def mock_subscription_response_beta(self):
        """Mock successful subscription lookup response for BETA plan."""
        return {
            "items": [
                {
                    "subscription_id": "sub_789",
                    "customer_id": "customer_456",
                    "product_id": "beta_product_456",
                    "status": "active",
                    "created_at": "2023-11-07T05:31:56Z",
                    "currency": "USD",
                    "recurring_pre_tax_amount": 0.00,
                }
            ]
        }

    @pytest.fixture
    def mock_multiple_subscriptions_response(self):
        """Mock response with multiple subscriptions to test sorting."""
        return {
            "items": [
                {
                    "subscription_id": "sub_old",
                    "customer_id": "customer_456",
                    "product_id": "pro_product_123",
                    "status": "active",
                    "created_at": "2023-11-07T05:31:56Z",
                    "currency": "USD",
                    "recurring_pre_tax_amount": 29.99,
                },
                {
                    "subscription_id": "sub_new",
                    "customer_id": "customer_456",
                    "product_id": "pro_product_123",
                    "status": "active",
                    "created_at": "2023-12-07T05:31:56Z",
                    "currency": "USD",
                    "recurring_pre_tax_amount": 29.99,
                },
            ]
        }

    @pytest.mark.asyncio
    async def test_get_user_plan_no_api_key(self):
        """Test get_user_plan returns BETA when DODO_API_KEY is not configured."""
        with patch.dict(os.environ, {}, clear=True):
            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_customer_not_found(self):
        """Test get_user_plan returns BETA when customer is not found."""
        with (
            patch("user.DODO_API_KEY", "test_dodo_key"),
            patch("user.PRO_PLAN_PRODUCT_ID", "pro_product_123"),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Mock the context manager
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock empty customer response
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"items": []}
            mock_client.get.return_value = mock_response

            result = await user.get_user_plan("nonexistent@example.com")
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_no_active_subscriptions(self, mock_customer_response):
        """Test get_user_plan returns BETA when no active subscriptions found."""
        with (
            patch("user.DODO_API_KEY", "test_dodo_key"),
            patch("user.PRO_PLAN_PRODUCT_ID", "pro_product_123"),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Mock the context manager
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client

            # Mock customer response
            mock_customer_resp = AsyncMock()
            mock_customer_resp.status_code = 200
            mock_customer_resp.json.return_value = mock_customer_response

            # Mock empty subscription response
            mock_subscription_resp = AsyncMock()
            mock_subscription_resp.status_code = 200
            mock_subscription_resp.json.return_value = {"items": []}

            mock_client.get.side_effect = [mock_customer_resp, mock_subscription_resp]

            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_pro_subscription(self, mock_customer_response, mock_subscription_response):
        """Test get_user_plan returns PRO when user has matching PRO subscription."""
        with (
            patch("user.DODO_API_KEY", "test_dodo_key"),
            patch("user.PRO_PLAN_PRODUCT_ID", "pro_product_123"),
            patch("user._get_customer_id_by_email", return_value="customer_456"),
            patch("user._get_latest_active_subscription", return_value=mock_subscription_response["items"][0]),
        ):
            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.PRO

    @pytest.mark.asyncio
    async def test_get_user_plan_beta_subscription(self, mock_customer_response, mock_subscription_response_beta):
        """Test get_user_plan returns BETA when user has non-PRO subscription."""
        with (
            patch("user.DODO_API_KEY", "test_dodo_key"),
            patch("user.PRO_PLAN_PRODUCT_ID", "pro_product_123"),
            patch("user._get_customer_id_by_email", return_value="customer_456"),
            patch("user._get_latest_active_subscription", return_value=mock_subscription_response_beta["items"][0]),
        ):
            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_multiple_subscriptions_latest(self, mock_customer_response):
        """Test get_user_plan uses latest subscription when multiple exist."""
        with (
            patch("user.DODO_API_KEY", "test_dodo_key"),
            patch("user.PRO_PLAN_PRODUCT_ID", "pro_product_123"),
            patch("user._get_customer_id_by_email", return_value="customer_456"),
            patch(
                "user._get_latest_active_subscription",
                return_value={
                    "subscription_id": "sub_new",
                    "customer_id": "customer_456",
                    "product_id": "pro_product_123",
                    "status": "active",
                    "created_at": "2023-12-07T05:31:56Z",
                    "currency": "USD",
                    "recurring_pre_tax_amount": 29.99,
                },
            ),
        ):
            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.PRO

    @pytest.mark.asyncio
    async def test_get_user_plan_api_error_customer_lookup(self):
        """Test get_user_plan returns BETA when customer API returns error."""
        with patch.dict(os.environ, {"DODO_API_KEY": "test_key"}), patch("httpx.AsyncClient.get") as mock_get:
            # Mock customer API error
            mock_response = AsyncMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_get.return_value = mock_response

            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_api_error_subscription_lookup(self, mock_customer_response):
        """Test get_user_plan returns BETA when subscription API returns error."""
        with patch.dict(os.environ, {"DODO_API_KEY": "test_key"}), patch("httpx.AsyncClient.get") as mock_get:
            # Mock customer response
            mock_customer_resp = AsyncMock()
            mock_customer_resp.status_code = 200
            mock_customer_resp.json.return_value = mock_customer_response

            # Mock subscription API error
            mock_subscription_resp = AsyncMock()
            mock_subscription_resp.status_code = 404
            mock_subscription_resp.text = "Not Found"

            mock_get.side_effect = [mock_customer_resp, mock_subscription_resp]

            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_timeout_error(self):
        """Test get_user_plan returns BETA when API calls timeout."""
        with patch.dict(os.environ, {"DODO_API_KEY": "test_key"}), patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Request timeout")

            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_network_error(self):
        """Test get_user_plan returns BETA when network errors occur."""
        with patch.dict(os.environ, {"DODO_API_KEY": "test_key"}), patch("httpx.AsyncClient.get") as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection failed")

            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_json_parse_error(self):
        """Test get_user_plan returns BETA when JSON parsing fails."""
        with patch.dict(os.environ, {"DODO_API_KEY": "test_key"}), patch("httpx.AsyncClient.get") as mock_get:
            # Mock response with invalid JSON
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = ValueError("Invalid JSON")
            mock_get.return_value = mock_response

            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_no_pro_plan_product_id(self, mock_customer_response, mock_subscription_response):
        """Test get_user_plan returns BETA when PRO_PLAN_PRODUCT_ID is not configured."""
        with (
            patch.dict(os.environ, {"DODO_API_KEY": "test_key"}, clear=True),
            patch("httpx.AsyncClient.get") as mock_get,
        ):
            # Mock customer response
            mock_customer_resp = AsyncMock()
            mock_customer_resp.status_code = 200
            mock_customer_resp.json.return_value = mock_customer_response

            # Mock subscription response
            mock_subscription_resp = AsyncMock()
            mock_subscription_resp.status_code = 200
            mock_subscription_resp.json.return_value = mock_subscription_response

            mock_get.side_effect = [mock_customer_resp, mock_subscription_resp]

            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_api_calls_correct_endpoints(self, mock_customer_response, mock_subscription_response):
        """Test get_user_plan makes correct API calls to Dodo Payments."""
        with (
            patch("user.DODO_API_KEY", "test_dodo_key"),
            patch("user.PRO_PLAN_PRODUCT_ID", "pro_product_123"),
            patch("user._get_customer_id_by_email", return_value="customer_456") as mock_customer_lookup,
            patch(
                "user._get_latest_active_subscription", return_value=mock_subscription_response["items"][0]
            ) as mock_subscription_lookup,
        ):
            await user.get_user_plan("test@example.com")

            # Verify that both functions were called
            mock_customer_lookup.assert_called_once_with("test@example.com")
            mock_subscription_lookup.assert_called_once_with("customer_456")

    @pytest.mark.asyncio
    async def test_get_user_plan_subscription_sorting_by_created_at(self, mock_customer_response):
        """Test get_user_plan correctly sorts subscriptions by created_at field."""
        with (
            patch("user.DODO_API_KEY", "test_dodo_key"),
            patch("user.PRO_PLAN_PRODUCT_ID", "pro_product_123"),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Mock the context manager
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)

            # Mock customer response
            mock_customer_resp = AsyncMock()
            mock_customer_resp.status_code = 200
            mock_customer_resp.json.return_value = mock_customer_response

            # Mock subscriptions with different creation dates
            mock_subscription_resp = AsyncMock()
            mock_subscription_resp.status_code = 200
            mock_subscription_resp.json.return_value = {
                "items": [
                    {
                        "subscription_id": "sub_old",
                        "customer_id": "customer_456",
                        "product_id": "pro_product_123",
                        "status": "active",
                        "created_at": "2023-10-07T05:31:56Z",
                        "currency": "USD",
                        "recurring_pre_tax_amount": 29.99,
                    },
                    {
                        "subscription_id": "sub_new",
                        "customer_id": "customer_456",
                        "product_id": "beta_product_456",
                        "status": "active",
                        "created_at": "2023-12-07T05:31:56Z",
                        "currency": "USD",
                        "recurring_pre_tax_amount": 0.00,
                    },
                ]
            }

            mock_client.get.side_effect = [mock_customer_resp, mock_subscription_resp]

            result = await user.get_user_plan("test@example.com")
            # Should use the latest subscription (beta_product_456) which is BETA
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_handles_missing_customer_fields(self):
        """Test get_user_plan handles missing fields in customer response."""
        with (
            patch("user.DODO_API_KEY", "test_dodo_key"),
            patch("user.PRO_PLAN_PRODUCT_ID", "pro_product_123"),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Mock the context manager
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)

            # Mock customer response with missing customer_id
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "items": [
                    {
                        "business_id": "business_123",
                        "created_at": "2023-11-07T05:31:56Z",
                        "email": "test@example.com",
                        "name": "Test User",
                        # Missing customer_id
                    }
                ]
            }
            mock_client.get.return_value = mock_response

            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_handles_missing_subscription_fields(self, mock_customer_response):
        """Test get_user_plan handles missing fields in subscription response."""
        with (
            patch("user.DODO_API_KEY", "test_dodo_key"),
            patch("user.PRO_PLAN_PRODUCT_ID", "pro_product_123"),
            patch("httpx.AsyncClient.get") as mock_get,
        ):
            # Mock customer response
            mock_customer_resp = AsyncMock()
            mock_customer_resp.status_code = 200
            mock_customer_resp.json.return_value = mock_customer_response

            # Mock subscription response with missing product_id
            mock_subscription_resp = AsyncMock()
            mock_subscription_resp.status_code = 200
            mock_subscription_resp.json.return_value = {
                "items": [
                    {
                        "subscription_id": "sub_789",
                        "customer_id": "customer_456",
                        "status": "active",
                        "created_at": "2023-11-07T05:31:56Z",
                        "currency": "USD",
                        # Missing product_id
                    }
                ]
            }

            mock_get.side_effect = [mock_customer_resp, mock_subscription_resp]

            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.BETA

    @pytest.mark.asyncio
    async def test_get_user_plan_handles_invalid_created_at_format(self, mock_customer_response):
        """Test get_user_plan handles invalid created_at format in subscriptions."""
        with (
            patch("user.DODO_API_KEY", "test_dodo_key"),
            patch("user.PRO_PLAN_PRODUCT_ID", "pro_product_123"),
            patch("httpx.AsyncClient") as mock_client_class,
        ):
            # Mock the context manager
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)

            # Mock customer response
            mock_customer_resp = AsyncMock()
            mock_customer_resp.status_code = 200
            mock_customer_resp.json.return_value = mock_customer_response

            # Mock subscription response with invalid created_at
            mock_subscription_resp = AsyncMock()
            mock_subscription_resp.status_code = 200
            mock_subscription_resp.json.return_value = {
                "items": [
                    {
                        "subscription_id": "sub_789",
                        "customer_id": "customer_456",
                        "product_id": "pro_product_123",
                        "status": "active",
                        "created_at": "invalid-date-format",
                        "currency": "USD",
                        "recurring_pre_tax_amount": 29.99,
                    }
                ]
            }

            mock_client.get.side_effect = [mock_customer_resp, mock_subscription_resp]

            result = await user.get_user_plan("test@example.com")
            assert result == UserPlan.BETA
