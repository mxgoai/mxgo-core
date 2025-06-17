import json
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest  # For fixtures

# Corrected import for FakeAsyncRedis based on common usage and docs
from fakeredis import FakeAsyncRedis
from fastapi.testclient import TestClient
from freezegun import freeze_time  # For controlling time in tests

from mxtoai._logging import get_logger
from mxtoai.api import app

client = TestClient(app) # This client might be overridden by fixtures for specific tests
API_KEY = os.environ["X_API_KEY"]

logger = get_logger(__name__)


# Test constants for rate limits to avoid magic numbers in tests, mirroring validators.py
# These should match what's in mxtoai.validators.py for the BETA plan
TEST_EMAIL_LIMIT_HOUR = 20
TEST_EMAIL_LIMIT_DAY = 50
TEST_EMAIL_LIMIT_MONTH = 300
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
    fake_redis_instance = FakeAsyncRedis() # Use the corrected import

    # Define a set of known provider domains for testing
    test_provider_domains = {TEST_KNOWN_PROVIDER_DOMAIN}

    # Use a context manager for the app to handle startup/shutdown
    with TestClient(app) as test_client:
        # Patch after the app's lifespan has initialized the real client
        with patch("mxtoai.validators.redis_client", new=fake_redis_instance), \
             patch("mxtoai.validators.email_provider_domain_set", new=test_provider_domains):

            # It's important that the fake_redis_instance is used by the application.
            # The lifespan manager in api.py sets mxtoai.validators.redis_client.
            # We are effectively replacing it here for the test's scope.
            # To ensure our mock is used, we might need to ensure this patching happens
            # *after* the app's startup sequence or that the app's startup uses a
            # reference that we can control.
            # A simpler way if the app is re-initialized per test or test session for TestClient:
            # we can assume the patch takes effect before request handling.

            # Forcing the global in validators to be our fake instance
            import mxtoai.validators
            original_redis_client = mxtoai.validators.redis_client
            original_domain_set = mxtoai.validators.email_provider_domain_set

            mxtoai.validators.redis_client = fake_redis_instance
            mxtoai.validators.email_provider_domain_set = test_provider_domains

            yield test_client # Test runs here

            # Teardown: clear fake redis and restore original globals
            # fake_redis_instance.flushall() # fakeredis might not have async flushall, use sync version for setup/teardown
            # For FakeAsyncRedis, usually it's per-instance, so just letting it go out of scope is fine.
            # Or, if it's a singleton from fakeredis, you might need fake_redis_instance.client.flushall()
            # For now, assume FakeAsyncRedis instances are independent.

            # Restore original globals to prevent interference between tests if not using function scope for everything
            mxtoai.validators.redis_client = original_redis_client
            mxtoai.validators.email_provider_domain_set = original_domain_set


def prepare_form_data(**kwargs):
    form_data = {
        "from_email": "test@example.com",
        "to": "ask@mxtoai.com",
        "subject": "Test Subject",
        "textContent": "Test text content",
        "htmlContent": "<p>Test HTML content</p>",
        "messageId": f"test-message-id-{os.urandom(4).hex()}",
        "date": "2023-10-26T10:00:00Z",
        "rawHeaders": '{"cc": "cc@example.com"}',
    }
    for key, value in kwargs.items():
        form_data[key] = value
    return form_data

def make_post_request_with_client(test_client, form_data, endpoint, files=None, headers=None):
    request_headers = {"x-api-key": API_KEY}
    if headers is not None:
        request_headers.update(headers)
    if request_headers.get("x-api-key") is None and "x-api-key" in request_headers:
        del request_headers["x-api-key"]
    return test_client.post(endpoint, data=form_data, files=files, headers=request_headers)


def make_post_request(form_data, endpoint, files=None, headers=None): # Keep for non-rate-limit tests
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
@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
def test_process_email_success_no_attachments_ask_handle(mock_task_send, mock_validate_email_whitelist, client_with_patched_redis):
    mock_validate_email_whitelist.return_value = None
    form_data = prepare_form_data(to="ask@mxtoai.com", from_email="pass@example.com") # Use unique email

    response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
    assert_successful_response(response, expected_attachments_saved=0)
    mock_validate_email_whitelist.assert_called_once()
    validate_send_task(form_data, mock_task_send, expected_attachment_count=0)


# ... (other existing tests - ensure they use client_with_patched_redis and unique from_email if needed) ...

# --- New Rate Limiting Tests ---

@freeze_time("2024-01-15 10:00:00 UTC")
@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock) # Still mock this
@patch("mxtoai.api.process_email_task.send") # And this
@patch("mxtoai.validators.send_email_reply", new_callable=AsyncMock) # Mock rejection email
def test_email_hourly_rate_limit_exceeded(mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis):
    mock_validate_whitelist.return_value = None # Assume email is whitelisted
    test_email = f"hourly_limited_{os.urandom(2).hex()}@test.com"
    form_data_template = prepare_form_data(from_email=test_email, to="ask@mxtoai.com")

    for i in range(TEST_EMAIL_LIMIT_HOUR):
        form_data = {**form_data_template, "messageId": f"hourly-ok-{i}-{os.urandom(2).hex()}"}
        response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
        assert_successful_response(response)
        mock_task_send.reset_mock() # Reset for next call in loop

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
@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
@patch("mxtoai.validators.send_email_reply", new_callable=AsyncMock)
def test_email_daily_rate_limit_exceeded(mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis):
    mock_validate_whitelist.return_value = None
    test_email = f"daily_limited_{os.urandom(2).hex()}@test.com"
    form_data_template = prepare_form_data(from_email=test_email, to="ask@mxtoai.com")

    # Simulate requests spread over different hours but within the same day
    for i in range(TEST_EMAIL_LIMIT_DAY):
        with freeze_time(datetime(2024, 1, 15, 10 + (i // TEST_EMAIL_LIMIT_HOUR), i % 60, 0, tzinfo=timezone.utc)):
            form_data = {**form_data_template, "messageId": f"daily-ok-{i}-{os.urandom(2).hex()}"}
            response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
            if response.status_code != 200: # If it hits hourly limit before daily, that's also a valid intermediate state for this test setup
                assert_rate_limit_exceeded_response(response, "email hour")
                mock_rejection_email.assert_called()
                mock_rejection_email.reset_mock()
                mock_task_send.assert_not_called() # Should not proceed if rate limited
            else:
                assert_successful_response(response)
            mock_task_send.reset_mock() # Reset for next call

    # Next request on the same day should exceed daily limit
    with freeze_time(datetime(2024, 1, 15, 23, 0, 0, tzinfo=timezone.utc)):
        form_data = {**form_data_template, "messageId": f"daily-exceed-{os.urandom(2).hex()}"}
        response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
        assert_rate_limit_exceeded_response(response, "email day for beta plan")
        mock_task_send.assert_not_called()
        mock_rejection_email.assert_called() # Should have been called at least once for the daily limit


@freeze_time("2024-01-15 10:00:00 UTC")
@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
@patch("mxtoai.validators.send_email_reply", new_callable=AsyncMock)
def test_email_monthly_rate_limit_exceeded(mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis):
    mock_validate_whitelist.return_value = None
    test_email = f"monthly_limited_{os.urandom(2).hex()}@test.com"
    form_data_template = prepare_form_data(from_email=test_email, to="ask@mxtoai.com")

    for i in range(TEST_EMAIL_LIMIT_MONTH):
        # Simulate requests spread over different days and hours within the same month
        day_of_month = 1 + (i // TEST_EMAIL_LIMIT_DAY)
        hour_of_day = 10 + ((i % TEST_EMAIL_LIMIT_DAY) // TEST_EMAIL_LIMIT_HOUR)
        day_of_month = min(day_of_month, 28) # Keep it simple for test month
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
@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
@patch("mxtoai.validators.send_email_reply", new_callable=AsyncMock)
def test_domain_hourly_rate_limit_exceeded_for_unknown_domain(mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis):
    mock_validate_whitelist.return_value = None

    for i in range(TEST_DOMAIN_LIMIT_HOUR):
        # Use different emails from the same unknown domain
        test_email = f"user{i}_{os.urandom(1).hex()}@{TEST_UNKNOWN_DOMAIN}"
        form_data = prepare_form_data(from_email=test_email, to="ask@mxtoai.com", messageId=f"domain-ok-{i}-{os.urandom(2).hex()}")
        response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")
        assert_successful_response(response)
        mock_task_send.reset_mock()
        mock_validate_whitelist.reset_mock() # Reset for next distinct email call

    # Next request from any user on this domain should exceed
    test_email_exceed = f"user_exceed_{os.urandom(1).hex()}@{TEST_UNKNOWN_DOMAIN}"
    form_data_exceed = prepare_form_data(from_email=test_email_exceed, to="ask@mxtoai.com", messageId=f"domain-exceed-{os.urandom(2).hex()}")
    response = make_post_request_with_client(client_with_patched_redis, form_data_exceed, "/process-email")
    assert_rate_limit_exceeded_response(response, "domain hour")
    mock_task_send.assert_not_called()
    mock_rejection_email.assert_called_once()
    # Whitelist for this specific exceeding email should not have been called
    mock_validate_whitelist.assert_not_called()


@freeze_time("2024-01-15 10:00:00 UTC")
@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
@patch("mxtoai.validators.send_email_reply", new_callable=AsyncMock)
def test_domain_limit_not_applied_for_known_provider(mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis):
    mock_validate_whitelist.return_value = None

    # Send more than TEST_DOMAIN_LIMIT_HOUR requests from a known provider domain
    # These should only be limited by their per-email limits, not the general domain limit.
    for i in range(TEST_DOMAIN_LIMIT_HOUR + 5): # Go over the general domain limit
        test_email = f"user{i}_{os.urandom(1).hex()}@{TEST_KNOWN_PROVIDER_DOMAIN}"
        form_data = prepare_form_data(from_email=test_email, to="ask@mxtoai.com", messageId=f"known-domain-{i}-{os.urandom(2).hex()}")
        response = make_post_request_with_client(client_with_patched_redis, form_data, "/process-email")

        # It might hit per-email hour limit if user{i} is repeated many times by chance of os.urandom(1)
        # For simplicity, we assume each user{i} is unique enough not to hit *its own* email limit within this loop
        # The main point is that it shouldn't hit the *domain* limit for knownprovider.com
        assert_successful_response(response)
        mock_task_send.reset_mock()
        mock_validate_whitelist.reset_mock()

    mock_rejection_email.assert_not_called() # No domain rate limit rejection


@freeze_time("2024-01-15 10:00:00 UTC")
@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
@patch("mxtoai.validators.send_email_reply", new_callable=AsyncMock)
def test_email_normalization_for_rate_limiting(mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis):
    mock_validate_whitelist.return_value = None
    base_email = f"normalized_user_{os.urandom(2).hex()}"
    domain = "testnorm.com"

    email1 = f"{base_email}@{domain}"
    email2 = f"{base_email}+alias1@{domain}"
    email3 = f"{base_email}+another.alias@{domain.upper()}" # Test domain case insensitivity too

    form_data_template = prepare_form_data(to="ask@mxtoai.com")

    # Send up to the hourly limit using variations of the same base email
    for i in range(TEST_EMAIL_LIMIT_HOUR):
        current_email = [email1, email2, email3][i % 3]
        form_data = {**form_data_template, "from_email": current_email, "messageId": f"norm-ok-{i}-{os.urandom(2).hex()}"}
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
@patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
@patch("mxtoai.api.process_email_task.send")
@patch("mxtoai.validators.send_email_reply", new_callable=AsyncMock)
def test_rate_limits_cleared_after_time_period(mock_rejection_email, mock_task_send, mock_validate_whitelist, client_with_patched_redis):
    mock_validate_whitelist.return_value = None
    test_email = f"time_cleared_{os.urandom(2).hex()}@test.com"
    form_data_template = prepare_form_data(from_email=test_email, to="ask@mxtoai.com")

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
        form_data_success_next_hour = {**form_data_template, "messageId": f"clear-success-next-hour-{os.urandom(2).hex()}"}
        response = make_post_request_with_client(client_with_patched_redis, form_data_success_next_hour, "/process-email")
        assert_successful_response(response)
        mock_task_send.assert_called_once() # Should be processed
        mock_rejection_email.assert_not_called() # No rejection this time
