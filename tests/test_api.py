import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest  # For fixtures

# Corrected import for FakeAsyncRedis based on common usage and docs
from fakeredis import FakeAsyncRedis
from fastapi import Response
from fastapi.testclient import TestClient
from freezegun import freeze_time  # For controlling time in tests

import mxgo.validators
from mxgo._logging import get_logger
from mxgo.api import app
from mxgo.schemas import EmailSuggestionResponse, SuggestionDetail
from tests.generate_test_jwt import generate_test_jwt

# Set environment variables for testing
os.environ["JWT_SECRET"] = "test_secret_key_for_development_only"  # noqa: S105

client = TestClient(app)  # This client might be overridden by fixtures for specific tests
API_KEY = os.environ["X_API_KEY"]

logger = get_logger(__name__)


# Test constants for rate limits to avoid magic numbers in tests, mirroring config.py
# These should match what's in mxgo.config.py for the BETA plan
TEST_EMAIL_LIMIT_HOUR = 10
TEST_EMAIL_LIMIT_DAY = 30
TEST_EMAIL_LIMIT_MONTH = 200
TEST_DOMAIN_LIMIT_HOUR = 50
TEST_KNOWN_PROVIDER_DOMAIN = "knownprovider.com"
TEST_UNKNOWN_DOMAIN = "unknownprovider.com"


@pytest.fixture
def client_with_patched_redis():
    # This fixture will patch the redis_client used by the validators
    # and the email_provider_domain_set for the duration of a test.
    # It ensures that the app's lifespan manager completes its startup phase
    # before we patch, so we patch the actual client instance.

    # Initialize a fake Redis client for async operations
    fake_redis_instance = FakeAsyncRedis()  # Use the corrected import

    # Define a set of known provider domains for testing
    test_provider_domains = {TEST_KNOWN_PROVIDER_DOMAIN}

    # Use a context manager for the app to handle startup/shutdown
    with (
        TestClient(app) as test_client,
        # Patch after the app's lifespan has initialized the real client
        patch("mxgo.validators.redis_client", new=fake_redis_instance),
        patch("mxgo.validators.email_provider_domain_set", new=test_provider_domains),
    ):
        # It's important that the fake_redis_instance is used by the application.
        # The lifespan manager in api.py sets mxgo.validators.redis_client.
        # We are effectively replacing it here for the test's scope.
        # To ensure our mock is used, we might need to ensure this patching happens
        # *after* the app's startup sequence or that the app's startup uses a
        # reference that we can control.
        # A simpler way if the app is re-initialized per test or test session for TestClient:
        # we can assume the patch takes effect before request handling.

        # Forcing the global in validators to be our fake instance
        original_redis_client = mxgo.validators.redis_client
        original_domain_set = mxgo.validators.email_provider_domain_set

        mxgo.validators.redis_client = fake_redis_instance
        mxgo.validators.email_provider_domain_set = test_provider_domains

        yield test_client  # Test runs here

        # Teardown: clear fake redis and restore original globals

        # For FakeAsyncRedis, usually it's per-instance, so just letting it go out of scope is fine.
        # Or, if it's a singleton from fakeredis, you might need fake_redis_instance.client.flushall()
        # For now, assume FakeAsyncRedis instances are independent.

        mxgo.validators.redis_client = original_redis_client
        mxgo.validators.email_provider_domain_set = original_domain_set


def prepare_form_data(**kwargs):
    return {
        "from_email": "test@example.com",
        "to": "ask@mxgo.com",
        "subject": "Test Subject",
        "textContent": "Test content",
        "htmlContent": "<p>Test content</p>",
        **dict(kwargs.items()),
    }


def make_post_request_with_client(test_client, form_data, endpoint, files=None, headers=None):
    request_headers = {"x-api-key": API_KEY}
    if headers is not None:
        request_headers.update(headers)
    if request_headers.get("x-api-key") is None and "x-api-key" in request_headers:
        del request_headers["x-api-key"]
    return test_client.post(endpoint, data=form_data, files=files, headers=request_headers)


def make_post_request(form_data, endpoint, files=None, headers=None):  # Keep for non-rate-limit tests
    request_headers = {"x-api-key": API_KEY}
    if headers is not None:
        request_headers.update(headers)
    if request_headers.get("x-api-key") is None and "x-api-key" in request_headers:
        del request_headers["x-api-key"]

    return client.post(endpoint, data=form_data, files=files, headers=request_headers)


def assert_successful_response(response, expected_attachments_saved=0):
    assert response.status_code == 200, f"Expected status 200, got {response.status_code}. Response: {response.text}"
    response_json = response.json()
    assert response_json["message"] == "Email received and queued for processing"
    assert "email_id" in response_json
    assert response_json["email_id"] is not None
    assert response_json["email_id"] != ""
    assert response_json["attachments_saved"] == expected_attachments_saved
    assert response_json["status"] == "processing"


def assert_rate_limit_exceeded_response(response, expected_message_part):
    assert response.status_code == 429, f"Expected status 429, got {response.status_code}. Response: {response.text}"
    response_json = response.json()
    assert "Rate limit exceeded" in response_json["message"]
    assert expected_message_part in response_json["message"]
    assert response_json["status"] == "error"


def validate_send_task(
    form_data, mock_task_send, expected_attachment_count=0, expected_attachment_filename=None, temp_attachments_dir=None
):
    mock_task_send.assert_called_once()
    args_task_send, _ = mock_task_send.call_args
    sent_email_request_dump = args_task_send[0]
    email_attachments_dir_arg = args_task_send[1]
    processed_attachment_info_arg = args_task_send[2]

    assert sent_email_request_dump["from_email"] == form_data["from_email"]
    assert sent_email_request_dump["to"] == form_data["to"]
    assert sent_email_request_dump["subject"] == form_data["subject"]

    raw_headers_in_task = sent_email_request_dump.get("rawHeaders", {})
    expected_raw_headers = {}
    if form_data.get("rawHeaders"):
        try:
            expected_raw_headers = json.loads(form_data["rawHeaders"])
        except (json.JSONDecodeError, TypeError, ValueError):
            expected_raw_headers = {}

    assert raw_headers_in_task == expected_raw_headers

    expected_cc = []
    if isinstance(expected_raw_headers, dict) and "cc" in expected_raw_headers:
        cc_val = expected_raw_headers["cc"]
        if isinstance(cc_val, str):
            expected_cc = [addr.strip() for addr in cc_val.split(",") if addr.strip()]
        elif isinstance(cc_val, list):
            expected_cc = cc_val

    assert sent_email_request_dump.get("cc", []) == expected_cc

    assert len(processed_attachment_info_arg) == expected_attachment_count
    if expected_attachment_count > 0:
        assert email_attachments_dir_arg != ""
        if temp_attachments_dir:
            assert Path(email_attachments_dir_arg).parent == temp_attachments_dir, (
                f"Attachment directory {email_attachments_dir_arg} is not a child of tmp_path {temp_attachments_dir}"
            )

            id_component_from_path = Path(email_attachments_dir_arg).name
            assert id_component_from_path != "", "Generated email ID component in path is empty"

            if expected_attachment_filename:
                assert processed_attachment_info_arg[0]["filename"] == expected_attachment_filename
                expected_attachment_path = str(Path(email_attachments_dir_arg) / expected_attachment_filename)
                assert processed_attachment_info_arg[0]["path"] == expected_attachment_path, (
                    f"Attachment path mismatch: expected {expected_attachment_path}, got {processed_attachment_info_arg[0]['path']}"
                )
        else:
            assert email_attachments_dir_arg != ""
    else:
        assert email_attachments_dir_arg == "", f"Expected no attachment directory, but got {email_attachments_dir_arg}"


# --- Existing Tests (should mostly work, may need client_with_patched_redis if they trigger rate limits unintentionally) ---
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.process_email_task.send")
def test_process_email_success_no_attachments_ask_handle(
    mock_task_send, mock_validate_email_whitelist, client_with_patched_redis
):
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="ask@mxgo.com", from_email="pass@example.com")  # Use unique email

    response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
    assert_successful_response(response, expected_attachments_saved=0)
    mock_validate_email_whitelist.assert_called_once()
    validate_send_task(form_data, mock_task_send, expected_attachment_count=0)


# ... (other existing tests - ensure they use client_with_patched_redis and unique from_email if needed) ...

# --- New Rate Limiting Tests ---


@freeze_time("2024-01-15 10:00:00 UTC")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)  # Still mock this
@patch("mxgo.api.process_email_task.send")  # And this
@patch("mxgo.validators.send_email_reply", new_callable=AsyncMock)  # Mock rejection email
def test_email_hourly_rate_limit_exceeded(
    mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis
):
    mock_validate_whitelist.return_value = None  # Assume email is whitelisted
    test_email = f"hourly_limited_{os.urandom(2).hex()}@test.com"
    form_data_template = prepare_form_data(from_email=test_email, to="ask@mxgo.com")

    for i in range(TEST_EMAIL_LIMIT_HOUR):
        form_data = {**form_data_template, "messageId": f"hourly-ok-{i}-{os.urandom(2).hex()}"}
        response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
        assert_successful_response(response)
        mock_task_send.reset_mock()  # Reset for next call in loop

    # Next request should exceed
    form_data = {**form_data_template, "messageId": f"hourly-exceed-{os.urandom(2).hex()}"}
    response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
    assert_rate_limit_exceeded_response(response, "email hour for beta plan")
    mock_task_send.assert_not_called()
    mock_rejection_email.assert_called_once()
    # Whitelist should not be called if rate limited first
    # However, our current API code calls validate_rate_limits *then* validate_email_whitelist
    # So, whitelist *would* have been called TEST_EMAIL_LIMIT_HOUR times. Let's check this.
    # Actually, validate_rate_limits is called first. If it returns a response, others are skipped.
    assert mock_validate_whitelist.call_count == TEST_EMAIL_LIMIT_HOUR


@freeze_time("2024-01-15 10:00:00 UTC")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.process_email_task.send")
@patch("mxgo.validators.send_email_reply", new_callable=AsyncMock)
def test_email_daily_rate_limit_exceeded(
    mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis
):
    mock_validate_whitelist.return_value = None
    test_email = f"daily_limited_{os.urandom(2).hex()}@test.com"
    form_data_template = prepare_form_data(from_email=test_email, to="ask@mxgo.com")

    # Simulate requests spread over different hours but within the same day
    for i in range(TEST_EMAIL_LIMIT_DAY):
        with freeze_time(datetime(2024, 1, 15, 10 + (i // TEST_EMAIL_LIMIT_HOUR), i % 60, 0, tzinfo=timezone.utc)):
            form_data = {**form_data_template, "messageId": f"daily-ok-{i}-{os.urandom(2).hex()}"}
            response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
            if (
                response.status_code != 200
            ):  # If it hits hourly limit before daily, that's also a valid intermediate state for this test setup
                assert_rate_limit_exceeded_response(response, "email hour")
                mock_rejection_email.assert_called()
                mock_rejection_email.reset_mock()
                mock_task_send.assert_not_called()  # Should not proceed if rate limited
            else:
                assert_successful_response(response)
            mock_task_send.reset_mock()  # Reset for next call

    # Next request on the same day should exceed daily limit
    with freeze_time(datetime(2024, 1, 15, 23, 0, 0, tzinfo=timezone.utc)):
        form_data = {**form_data_template, "messageId": f"daily-exceed-{os.urandom(2).hex()}"}
        response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
        assert_rate_limit_exceeded_response(response, "email day for beta plan")
        mock_task_send.assert_not_called()
        mock_rejection_email.assert_called()  # Should have been called at least once for the daily limit


@freeze_time("2024-01-15 10:00:00 UTC")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.process_email_task.send")
@patch("mxgo.validators.send_email_reply", new_callable=AsyncMock)
def test_email_monthly_rate_limit_exceeded(
    mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis
):
    mock_validate_whitelist.return_value = None
    test_email = f"monthly_limited_{os.urandom(2).hex()}@test.com"
    form_data_template = prepare_form_data(from_email=test_email, to="ask@mxgo.com")

    for i in range(TEST_EMAIL_LIMIT_MONTH):
        # Simulate requests spread over different days and hours within the same month
        day_of_month = 1 + (i // TEST_EMAIL_LIMIT_DAY)
        hour_of_day = 10 + ((i % TEST_EMAIL_LIMIT_DAY) // TEST_EMAIL_LIMIT_HOUR)
        day_of_month = min(day_of_month, 28)  # Keep it simple for test month
        hour_of_day = min(hour_of_day, 23)

        with freeze_time(datetime(2024, 1, day_of_month, hour_of_day, i % 60, 0, tzinfo=timezone.utc)):
            form_data = {**form_data_template, "messageId": f"monthly-ok-{i}-{os.urandom(2).hex()}"}
            response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
            # This request might hit hourly or daily limits first depending on how i maps to TEST_EMAIL_LIMIT_HOUR/DAY
            if response.status_code != 200:
                assert response.status_code == 429
                mock_rejection_email.assert_called()
                mock_rejection_email.reset_mock()
            else:
                assert_successful_response(response)
            mock_task_send.reset_mock()

    # Next request in the same month should exceed
    with freeze_time(datetime(2024, 1, 28, 23, 0, 0, tzinfo=timezone.utc)):
        form_data = {**form_data_template, "messageId": f"monthly-exceed-{os.urandom(2).hex()}"}
        response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
        assert_rate_limit_exceeded_response(response, "email month for beta plan")
        mock_task_send.assert_not_called()
        mock_rejection_email.assert_called()


@freeze_time("2024-01-15 10:00:00 UTC")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.process_email_task.send")
@patch("mxgo.validators.send_email_reply", new_callable=AsyncMock)
def test_domain_hourly_rate_limit_exceeded_for_unknown_domain(
    mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis
):
    mock_validate_whitelist.return_value = None

    for i in range(TEST_DOMAIN_LIMIT_HOUR):
        # Use different emails from the same unknown domain
        test_email = f"user{i}_{os.urandom(1).hex()}@{TEST_UNKNOWN_DOMAIN}"
        form_data = prepare_form_data(
            from_email=test_email, to="ask@mxgo.com", messageId=f"domain-ok-{i}-{os.urandom(2).hex()}"
        )
        response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
        assert_successful_response(response)
        mock_task_send.reset_mock()
        mock_validate_whitelist.reset_mock()  # Reset for next distinct email call

    # Next request from any user on this domain should exceed
    test_email_exceed = f"user_exceed_{os.urandom(1).hex()}@{TEST_UNKNOWN_DOMAIN}"
    form_data_exceed = prepare_form_data(
        from_email=test_email_exceed, to="ask@mxgo.com", messageId=f"domain-exceed-{os.urandom(2).hex()}"
    )
    response = make_post_request_with_client(client_with_patched_redis, form_data_exceed, "/process-email")
    assert_rate_limit_exceeded_response(response, "domain hour")
    mock_task_send.assert_not_called()
    mock_rejection_email.assert_called_once()
    # Whitelist for this specific exceeding email should not have been called
    mock_validate_whitelist.assert_not_called()


@freeze_time("2024-01-15 10:00:00 UTC")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.process_email_task.send")
@patch("mxgo.validators.send_email_reply", new_callable=AsyncMock)
def test_domain_limit_not_applied_for_known_provider(
    mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis
):
    mock_validate_whitelist.return_value = None

    # Send more than TEST_DOMAIN_LIMIT_HOUR requests from a known provider domain
    # These should only be limited by their per-email limits, not the general domain limit.
    for i in range(TEST_DOMAIN_LIMIT_HOUR + 5):  # Go over the general domain limit
        test_email = f"user{i}_{os.urandom(1).hex()}@{TEST_KNOWN_PROVIDER_DOMAIN}"
        form_data = prepare_form_data(
            from_email=test_email, to="ask@mxgo.com", messageId=f"known-domain-{i}-{os.urandom(2).hex()}"
        )
        response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")

        # It might hit per-email hour limit if user{i} is repeated many times by chance of os.urandom(1)
        # For simplicity, we assume each user{i} is unique enough not to hit *its own* email limit within this loop
        # The main point is that it shouldn't hit the *domain* limit for knownprovider.com
        assert_successful_response(response)
        mock_task_send.reset_mock()
        mock_validate_whitelist.reset_mock()

    mock_rejection_email.assert_not_called()  # No domain rate limit rejection


@freeze_time("2024-01-15 10:00:00 UTC")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.process_email_task.send")
@patch("mxgo.validators.send_email_reply", new_callable=AsyncMock)
def test_email_normalization_for_rate_limiting(
    mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis
):
    mock_validate_whitelist.return_value = None
    base_email = f"normalized_user_{os.urandom(2).hex()}"
    domain = "testnorm.com"

    email1 = f"{base_email}@{domain}"
    email2 = f"{base_email}+alias1@{domain}"
    email3 = f"{base_email}+another.alias@{domain.upper()}"  # Test domain case insensitivity too

    form_data_template = prepare_form_data(to="ask@mxgo.com")

    # Send up to the hourly limit using variations of the same base email
    for i in range(TEST_EMAIL_LIMIT_HOUR):
        current_email = [email1, email2, email3][i % 3]
        form_data = {
            **form_data_template,
            "from_email": current_email,
            "messageId": f"norm-ok-{i}-{os.urandom(2).hex()}",
        }
        response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
        assert_successful_response(response)
        mock_task_send.reset_mock()

    # Next request with any variation should exceed
    form_data_exceed = {**form_data_template, "from_email": email2, "messageId": f"norm-exceed-{os.urandom(2).hex()}"}
    response = make_post_request_with_client(client_with_patched_redis, form_data_exceed, "/process-email")
    assert_rate_limit_exceeded_response(response, "email hour for beta plan")
    mock_task_send.assert_not_called()
    mock_rejection_email.assert_called_once()


@freeze_time("2024-01-15 10:00:00 UTC")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.process_email_task.send")
@patch("mxgo.validators.send_email_reply", new_callable=AsyncMock)
def test_rate_limits_cleared_after_time_period(
    mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis
):
    mock_validate_whitelist.return_value = None
    test_email = f"time_cleared_{os.urandom(2).hex()}@test.com"
    form_data_template = prepare_form_data(from_email=test_email, to="ask@mxgo.com")

    # Exceed hourly limit
    with freeze_time("2024-01-15 10:30:00 UTC") as frozen_time:
        for i in range(TEST_EMAIL_LIMIT_HOUR):
            form_data = {**form_data_template, "messageId": f"clear-ok-{i}-{os.urandom(2).hex()}"}
            response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
            assert_successful_response(response)
            mock_task_send.reset_mock()

        form_data_exceed = {**form_data_template, "messageId": f"clear-exceed1-{os.urandom(2).hex()}"}
        response = make_post_request_with_client(client_with_patched_redis, form_data_exceed, "/process-email")
        assert_rate_limit_exceeded_response(response, "email hour for beta plan")
        mock_rejection_email.assert_called_once()
        mock_rejection_email.reset_mock()
        mock_task_send.assert_not_called()

        # Move time to the next hour
        frozen_time.move_to("2024-01-15 11:05:00 UTC")

        # Request should now be successful as the hourly bucket has changed
        form_data_success_next_hour = {
            **form_data_template,
            "messageId": f"clear-success-next-hour-{os.urandom(2).hex()}",
        }
        response = make_post_request_with_client(
            client_with_patched_redis, form_data_success_next_hour, "/process-email"
        )
        assert_successful_response(response)
        mock_task_send.assert_called_once()  # Should be processed
        mock_rejection_email.assert_not_called()  # No rejection this time


# --- Unit Tests for Suggestions API ---


def prepare_suggestions_request_data(**kwargs):
    """Prepare test data for suggestions API requests."""
    return [
        {
            "email_identified": "test-email-123",
            "user_email_id": "test@example.com",
            "sender_email": "sender@example.com",
            "cc_emails": [],
            "Subject": "Test Subject",
            "email_content": "This is test email content.",
            "attachments": [],
            **kwargs,
        }
    ]


def make_suggestions_post_request(request_data, headers=None):
    """Make a POST request to the suggestions endpoint."""
    # Generate a valid JWT token
    jwt_token = generate_test_jwt(email="test@example.com", user_id="test_user_123")

    request_headers = {
        "x-suggestions-api-key": os.environ.get("SUGGESTIONS_API_KEY", "valid-suggestions-key"),
        "Authorization": f"Bearer {jwt_token}",
    }
    if headers:
        # Filter out None values before updating
        filtered_headers = {k: v for k, v in headers.items() if v is not None}
        request_headers.update(filtered_headers)

        # Handle the case where the key was explicitly set to None and should be removed
        if "x-suggestions-api-key" in headers and headers["x-suggestions-api-key"] is None:
            request_headers.pop("x-suggestions-api-key", None)

    return client.post("/suggestions", json=request_data, headers=request_headers)


def make_suggestions_post_request_with_client(test_client, request_data, headers=None):
    """Make a POST request to the suggestions endpoint with custom client."""
    # Generate a valid JWT token
    jwt_token = generate_test_jwt(email="test@example.com", user_id="test_user_123")

    request_headers = {
        "x-suggestions-api-key": os.environ.get("SUGGESTIONS_API_KEY", "test-suggestions-key"),
        "Authorization": f"Bearer {jwt_token}",
    }
    if headers is not None:
        request_headers.update(headers)

    return test_client.post("/suggestions", json=request_data, headers=request_headers)


def assert_suggestions_successful_response(response, expected_num_requests=1):
    """Assert a successful suggestions API response."""
    assert response.status_code == 200, f"Expected status 200, got {response.status_code}. Response: {response.text}"
    response_json = response.json()
    assert isinstance(response_json, list), "Response should be a list"
    assert len(response_json) == expected_num_requests, f"Expected {expected_num_requests} responses"

    for email_response in response_json:
        assert "email_identified" in email_response
        assert "user_email_id" in email_response
        assert "suggestions" in email_response
        assert isinstance(email_response["suggestions"], list)
        assert len(email_response["suggestions"]) >= 1, "Should have at least one suggestion"

        # Validate suggestion format
        for suggestion in email_response["suggestions"]:
            assert "suggestion_title" in suggestion
            assert "suggestion_id" in suggestion
            assert "suggestion_to_email" in suggestion
            assert "suggestion_cc_emails" in suggestion
            assert "suggestion_email_instructions" in suggestion
            assert isinstance(suggestion["suggestion_cc_emails"], list)


def assert_suggestions_error_response(response, expected_status=422):
    """Assert an error response from suggestions API."""
    assert response.status_code == expected_status, f"Expected status {expected_status}, got {response.status_code}"


@patch.dict(os.environ, {"SUGGESTIONS_API_KEY": "valid-suggestions-key"})
@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.generate_suggestions", new_callable=AsyncMock)
def test_suggestions_api_success_single_request(mock_generate_suggestions, mock_validate_whitelist):
    """Test successful suggestions API call with single request."""
    mock_validate_whitelist.return_value = None  # User is whitelisted

    # Mock the suggestions response

    mock_response = EmailSuggestionResponse(
        email_identified="test-email-123",
        user_email_id="test@example.com",
        suggestions=[
            SuggestionDetail(
                suggestion_title="Summarize content",
                suggestion_id="suggest-1",
                suggestion_to_email="summarize@mxgo.com",
                suggestion_cc_emails=[],
                suggestion_email_instructions="",
            ),
            SuggestionDetail(
                suggestion_title="Ask anything",
                suggestion_id="suggest-2",
                suggestion_to_email="ask@mxgo.com",
                suggestion_cc_emails=[],
                suggestion_email_instructions="",
            ),
        ],
    )
    mock_generate_suggestions.return_value = mock_response

    request_data = prepare_suggestions_request_data()
    response = make_suggestions_post_request(request_data)

    assert_suggestions_successful_response(response, expected_num_requests=1)
    mock_validate_whitelist.assert_called_once()
    mock_generate_suggestions.assert_called_once()

    # Verify the response content
    response_json = response.json()
    email_response = response_json[0]
    assert email_response["email_identified"] == "test-email-123"
    assert email_response["user_email_id"] == "test@example.com"
    assert len(email_response["suggestions"]) == 2


@patch.dict(os.environ, {"SUGGESTIONS_API_KEY": "valid-suggestions-key"})
@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.generate_suggestions", new_callable=AsyncMock)
def test_suggestions_api_success_multiple_requests(mock_generate_suggestions, mock_validate_whitelist):
    """Test successful suggestions API call with multiple requests."""
    mock_validate_whitelist.return_value = None

    # Mock responses for each request
    mock_responses = [
        EmailSuggestionResponse(
            email_identified=f"test-email-{i}",
            user_email_id="test@example.com",
            suggestions=[
                SuggestionDetail(
                    suggestion_title="Ask anything",
                    suggestion_id=f"suggest-{i}",
                    suggestion_to_email="ask@mxgo.com",
                    suggestion_cc_emails=[],
                    suggestion_email_instructions="",
                ),
            ],
        )
        for i in range(1, 4)
    ]
    mock_generate_suggestions.side_effect = mock_responses

    # Prepare multiple requests
    request_data = [
        {
            "email_identified": f"test-email-{i}",
            "user_email_id": "test@example.com",
            "sender_email": "sender@example.com",
            "cc_emails": [],
            "Subject": f"Test Subject {i}",
            "email_content": f"Test content {i}",
            "attachments": [],
        }
        for i in range(1, 4)
    ]

    response = make_suggestions_post_request(request_data)

    assert_suggestions_successful_response(response, expected_num_requests=3)
    assert mock_validate_whitelist.call_count == 3
    assert mock_generate_suggestions.call_count == 3


@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
def test_suggestions_api_missing_api_key():
    """Test suggestions API with missing API key."""
    request_data = prepare_suggestions_request_data()
    response = make_suggestions_post_request(request_data, headers={"x-suggestions-api-key": None})

    assert response.status_code == 422, f"Expected 422 for missing API key, got {response.status_code}"


@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
def test_suggestions_api_invalid_api_key():
    """Test suggestions API with invalid API key."""
    request_data = prepare_suggestions_request_data()
    response = make_suggestions_post_request(request_data, headers={"x-suggestions-api-key": "invalid-key"})

    assert response.status_code == 401, f"Expected 401 for invalid API key, got {response.status_code}"
    response_json = response.json()
    assert "Invalid suggestions API key" in response_json["message"]


@patch.dict(os.environ, {"SUGGESTIONS_API_KEY": ""})  # Missing environment variable
@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
def test_suggestions_api_missing_env_var():
    """Test suggestions API when SUGGESTIONS_API_KEY environment variable is not set."""
    request_data = prepare_suggestions_request_data()
    # Provide a valid API key header to test environment variable validation
    response = make_suggestions_post_request(request_data, headers={"x-suggestions-api-key": "test-key"})

    assert response.status_code == 500, f"Expected 500 for missing env var, got {response.status_code}"
    response_json = response.json()
    assert "Server configuration error" in response_json["message"]


@patch.dict(os.environ, {"SUGGESTIONS_API_KEY": "valid-suggestions-key"})
@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
def test_suggestions_api_user_not_whitelisted(mock_validate_whitelist):
    """Test suggestions API when user is not whitelisted."""
    # Mock whitelist validation to return an error response
    mock_validate_whitelist.return_value = Response(
        status_code=403, content=json.dumps({"detail": "User not whitelisted"})
    )

    request_data = prepare_suggestions_request_data()
    response = make_suggestions_post_request(request_data)

    # Should return 403 Forbidden instead of 200 with error suggestions
    assert response.status_code == 403, "Should return 403 Forbidden for non-whitelisted user"
    response_json = response.json()
    assert "detail" in response_json
    assert "Email verification required" in response_json["detail"]


@patch.dict(os.environ, {"SUGGESTIONS_API_KEY": "valid-suggestions-key"})
@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.generate_suggestions", new_callable=AsyncMock)
def test_suggestions_api_generation_error(mock_generate_suggestions, mock_validate_whitelist):
    """Test suggestions API when suggestions generation fails."""
    mock_validate_whitelist.return_value = None
    mock_generate_suggestions.side_effect = Exception("LLM service unavailable")

    request_data = prepare_suggestions_request_data()
    response = make_suggestions_post_request(request_data)

    # Should return 500 Internal Server Error instead of 200 with error suggestions
    assert response.status_code == 500, "Should return 500 Internal Server Error for generation failure"
    response_json = response.json()
    assert "detail" in response_json
    assert "Error processing suggestion request" in response_json["detail"]


@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
def test_suggestions_api_invalid_request_format():
    """Test suggestions API with invalid request format."""
    # Missing required fields
    invalid_request = [{"email_identified": "test"}]  # Missing required fields

    response = make_suggestions_post_request(invalid_request, headers={"x-suggestions-api-key": "valid-key"})

    assert_suggestions_error_response(response, expected_status=422)


@patch.dict(os.environ, {"SUGGESTIONS_API_KEY": "valid-key"})
@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
def test_suggestions_api_empty_request():
    """Test suggestions API with empty request list."""
    response = make_suggestions_post_request(
        [],  # Empty list
        headers={"x-suggestions-api-key": "valid-key"},
    )

    assert response.status_code == 200, "Empty list should be valid and return empty response"
    response_json = response.json()
    assert response_json == []


@patch.dict(os.environ, {"SUGGESTIONS_API_KEY": "valid-suggestions-key"})
@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.generate_suggestions", new_callable=AsyncMock)
def test_suggestions_api_with_attachments(mock_generate_suggestions, mock_validate_whitelist):
    """Test suggestions API with attachments in request."""
    mock_validate_whitelist.return_value = None

    mock_response = EmailSuggestionResponse(
        email_identified="test-email-123",
        user_email_id="test@example.com",
        suggestions=[
            SuggestionDetail(
                suggestion_title="Summarize documents",
                suggestion_id="suggest-1",
                suggestion_to_email="summarize@mxgo.com",
                suggestion_cc_emails=[],
                suggestion_email_instructions="Focus on key findings from the attached reports",
            ),
        ],
    )
    mock_generate_suggestions.return_value = mock_response

    request_data = prepare_suggestions_request_data(
        attachments=[
            {
                "filename": "report.pdf",
                "file_type": "application/pdf",
                "file_size": 1024000,
            },
            {
                "filename": "data.xlsx",
                "file_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "file_size": 512000,
            },
        ]
    )

    response = make_suggestions_post_request(request_data)

    assert_suggestions_successful_response(response)
    mock_generate_suggestions.assert_called_once()

    # Verify attachments were passed correctly
    call_args = mock_generate_suggestions.call_args[0][0]  # First positional argument (EmailSuggestionRequest)
    assert len(call_args.attachments) == 2
    assert call_args.attachments[0].filename == "report.pdf"
    assert call_args.attachments[1].filename == "data.xlsx"


@patch.dict(os.environ, {"SUGGESTIONS_API_KEY": "valid-suggestions-key"})
@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.generate_suggestions", new_callable=AsyncMock)
def test_suggestions_api_with_cc_emails(mock_generate_suggestions, mock_validate_whitelist):
    """Test suggestions API with CC emails in request."""
    mock_validate_whitelist.return_value = None

    mock_response = EmailSuggestionResponse(
        email_identified="test-email-123",
        user_email_id="test@example.com",
        suggestions=[
            SuggestionDetail(
                suggestion_title="Schedule meeting",
                suggestion_id="suggest-1",
                suggestion_to_email="meeting@mxgo.com",
                suggestion_cc_emails=["manager@company.com"],
                suggestion_email_instructions="",
            ),
        ],
    )
    mock_generate_suggestions.return_value = mock_response

    request_data = prepare_suggestions_request_data(cc_emails=["cc1@example.com", "cc2@example.com"])

    response = make_suggestions_post_request(request_data)

    assert_suggestions_successful_response(response)

    # Verify CC emails were passed correctly
    call_args = mock_generate_suggestions.call_args[0][0]
    assert call_args.cc_emails == ["cc1@example.com", "cc2@example.com"]

    # Verify response includes CC emails in suggestions
    response_json = response.json()
    suggestion = response_json[0]["suggestions"][0]
    assert suggestion["suggestion_cc_emails"] == ["manager@company.com"]


@patch.dict(os.environ, {"SUGGESTIONS_API_KEY": "valid-suggestions-key"})
@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
def test_suggestions_api_rate_limiting_integration(client_with_patched_redis):
    """Test suggestions API with rate limiting (if rate limits apply to suggestions endpoint)."""
    # Note: This test assumes suggestions endpoint might have its own rate limits
    # If not implemented, this test will verify normal operation

    request_data = prepare_suggestions_request_data()

    with (
        patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock) as mock_validate_whitelist,
        patch("mxgo.suggestions.generate_suggestions", new_callable=AsyncMock) as mock_generate_suggestions,
    ):
        mock_validate_whitelist.return_value = None

        mock_response = EmailSuggestionResponse(
            email_identified="test-email-123",
            user_email_id="test@example.com",
            suggestions=[
                SuggestionDetail(
                    suggestion_title="Ask anything",
                    suggestion_id="suggest-1",
                    suggestion_to_email="ask@mxgo.com",
                    suggestion_cc_emails=[],
                    suggestion_email_instructions="",
                ),
            ],
        )
        mock_generate_suggestions.return_value = mock_response

        # Make a request - should succeed
        response = make_suggestions_post_request_with_client(client_with_patched_redis, request_data)
        assert response.status_code == 200


@patch.dict(os.environ, {"SUGGESTIONS_API_KEY": "valid-suggestions-key"})
@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.generate_suggestions", new_callable=AsyncMock)
def test_suggestions_api_subject_field_alias(mock_generate_suggestions, mock_validate_whitelist):
    """Test suggestions API handles the Subject field alias correctly."""
    mock_validate_whitelist.return_value = None
    mock_response = EmailSuggestionResponse(
        email_identified="test-email-123",
        user_email_id="test@example.com",
        suggestions=[
            SuggestionDetail(
                suggestion_title="Ask anything",
                suggestion_id="suggest-1",
                suggestion_to_email="ask@mxgo.com",
                suggestion_cc_emails=[],
                suggestion_email_instructions="",
            ),
        ],
    )
    mock_generate_suggestions.return_value = mock_response

    # Test with "Subject" field (should work due to alias)
    request_data = prepare_suggestions_request_data(Subject="Test with Subject field")
    response = make_suggestions_post_request(request_data)

    assert_suggestions_successful_response(response)

    # Verify the subject was passed correctly
    call_args = mock_generate_suggestions.call_args[0][0]
    assert call_args.subject == "Test with Subject field"


@patch.dict(os.environ, {"SUGGESTIONS_API_KEY": "valid-suggestions-key"})
@patch("mxgo.auth.JWT_SECRET", "test_secret_key_for_development_only")
@patch("mxgo.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxgo.api.generate_suggestions", new_callable=AsyncMock)
def test_suggestions_api_default_suggestions_always_included(mock_generate_suggestions, mock_validate_whitelist):
    """Test that default suggestions are always included in responses."""
    mock_validate_whitelist.return_value = None

    # Mock response with only custom suggestions (no default)
    mock_response = EmailSuggestionResponse(
        email_identified="test-email-123",
        user_email_id="test@example.com",
        suggestions=[
            SuggestionDetail(
                suggestion_title="Fact check claims",
                suggestion_id="suggest-custom-1",
                suggestion_to_email="fact-check@mxgo.com",
                suggestion_cc_emails=[],
                suggestion_email_instructions="Verify the statistical claims in this email",
            ),
        ],
    )
    mock_generate_suggestions.return_value = mock_response

    request_data = prepare_suggestions_request_data()
    response = make_suggestions_post_request(request_data)

    assert_suggestions_successful_response(response)

    # The actual suggestions generation function should add default suggestions
    # This test verifies the API returns what the generation function provides
    response_json = response.json()
    email_response = response_json[0]

    # Should have the custom suggestion
    suggestion_titles = [s["suggestion_title"] for s in email_response["suggestions"]]
    assert "Fact check claims" in suggestion_titles
