import os
from unittest.mock import AsyncMock, patch

from fastapi import Response, status
from fastapi.testclient import TestClient

from mxtoai.api import app
from mxtoai.email_sender import generate_message_id
from mxtoai.tasks import process_email_task

API_KEY = os.environ["X_API_KEY"]


class TestIdempotency:
    """Test idempotency functionality for email processing."""

    def test_generate_message_id_deterministic(self):
        """Test that generate_message_id produces consistent results for same inputs."""
        # Test with same inputs
        msg_id_1 = generate_message_id(
            from_email="test@example.com",
            to="ask@mxtoai.com",
            subject="Test Subject",
            date="2023-01-01T12:00:00Z",
            html_content="<p>Test HTML</p>",
            text_content="Test text",
            files_count=2,
        )

        msg_id_2 = generate_message_id(
            from_email="test@example.com",
            to="ask@mxtoai.com",
            subject="Test Subject",
            date="2023-01-01T12:00:00Z",
            html_content="<p>Test HTML</p>",
            text_content="Test text",
            files_count=2,
        )

        assert msg_id_1 == msg_id_2, "Same inputs should produce same message ID"
        assert msg_id_1.startswith("<"), "Should start with <"
        assert msg_id_1.endswith("@mxtoai.com>"), "Should end with @mxtoai.com>"

        # Test with different inputs
        msg_id_3 = generate_message_id(
            from_email="different@example.com",  # Changed
            to="ask@mxtoai.com",
            subject="Test Subject",
            date="2023-01-01T12:00:00Z",
            html_content="<p>Test HTML</p>",
            text_content="Test text",
            files_count=2,
        )

        assert msg_id_1 != msg_id_3, "Different inputs should produce different message IDs"

    @patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
    @patch("mxtoai.api.validate_rate_limits", new_callable=AsyncMock)
    @patch("mxtoai.api.validate_idempotency", new_callable=AsyncMock)
    @patch("mxtoai.api.process_email_task")
    def test_api_idempotency_already_queued(
        self, mock_task, mock_validate_idempotency, mock_rate_limits, mock_validate_whitelist
    ):
        """Test API returns conflict when email already queued."""
        mock_validate_whitelist.return_value = None  # Email is whitelisted
        mock_rate_limits.return_value = None  # Rate limits pass

        # Mock idempotency check to return duplicate response
        duplicate_response = Response(
            content='{"message": "Email already queued for processing", "messageId": "<test123@example.com>", "status": "duplicate_queued"}',
            status_code=status.HTTP_409_CONFLICT,
            media_type="application/json",
        )
        mock_validate_idempotency.return_value = (duplicate_response, "<test123@example.com>")

        with TestClient(app) as test_client:
            form_data = {
                "from_email": "test@example.com",
                "to": "ask@mxtoai.com",
                "subject": "Test Subject",
                "textContent": "Test content",
                "messageId": "<test123@example.com>",
            }

            response = test_client.post("/process-email", data=form_data, headers={"x-api-key": API_KEY})

        assert response.status_code == 409
        response_data = response.json()
        assert response_data["status"] == "duplicate_queued"
        assert "already queued" in response_data["message"]

        # Task should not be called
        mock_task.send.assert_not_called()

    @patch("mxtoai.api.validate_email_whitelist", new_callable=AsyncMock)
    @patch("mxtoai.api.validate_rate_limits", new_callable=AsyncMock)
    @patch("mxtoai.api.validate_idempotency", new_callable=AsyncMock)
    @patch("mxtoai.api.process_email_task")
    def test_api_idempotency_already_processed(
        self, mock_task, mock_validate_idempotency, mock_rate_limits, mock_validate_whitelist
    ):
        """Test API returns conflict when email already processed."""
        mock_validate_whitelist.return_value = None  # Email is whitelisted
        mock_rate_limits.return_value = None  # Rate limits pass

        # Mock idempotency check to return duplicate response
        duplicate_response = Response(
            content='{"message": "Email already processed", "messageId": "<test123@example.com>", "status": "duplicate_processed"}',
            status_code=status.HTTP_409_CONFLICT,
            media_type="application/json",
        )
        mock_validate_idempotency.return_value = (duplicate_response, "<test123@example.com>")

        with TestClient(app) as test_client:
            form_data = {
                "from_email": "test@example.com",
                "to": "ask@mxtoai.com",
                "subject": "Test Subject",
                "textContent": "Test content",
                "messageId": "<test123@example.com>",
            }

            response = test_client.post("/process-email", data=form_data, headers={"x-api-key": API_KEY})

        assert response.status_code == 409
        response_data = response.json()
        assert response_data["status"] == "duplicate_processed"
        assert "already processed" in response_data["message"]

        # Task should not be called
        mock_task.send.assert_not_called()

    @patch("mxtoai.tasks.check_task_idempotency")
    def test_task_idempotency_already_processed(self, mock_check_idempotency):
        """Test task returns early when email already processed."""
        # Setup mock to return True (already processed)
        mock_check_idempotency.return_value = True

        email_data = {
            "from_email": "test@example.com",
            "to": "ask@mxtoai.com",
            "subject": "Test Subject",
            "textContent": "Test content",
            "messageId": "<test123@example.com>",
            "date": "2023-01-01T12:00:00Z",
            "rawHeaders": {},
            "cc": [],
            "attachments": [],
        }

        result = process_email_task(
            email_data=email_data, email_attachments_dir="", attachment_info=[], scheduled_task_id=None
        )

        # Should return duplicate result
        assert result.metadata.mode == "duplicate"
        assert result.metadata.email_sent.status == "duplicate"
        assert len(result.metadata.errors) == 1
        assert "already processed" in result.metadata.errors[0].message

    def test_generate_message_id_with_missing_message_id(self):
        """Test that missing messageId gets generated deterministically."""
        # Test empty/None messageId
        msg_id_1 = generate_message_id(
            from_email="test@example.com",
            to="ask@mxtoai.com",
            subject="Test Subject",
            date="2023-01-01T12:00:00Z",
            html_content="<p>Test HTML</p>",
            text_content="Test text",
            files_count=0,
        )

        msg_id_2 = generate_message_id(
            from_email="test@example.com",
            to="ask@mxtoai.com",
            subject="Test Subject",
            date="2023-01-01T12:00:00Z",
            html_content="<p>Test HTML</p>",
            text_content="Test text",
            files_count=0,
        )

        assert msg_id_1 == msg_id_2, "Should generate same ID for same content"
        assert len(msg_id_1) > 10, "Generated ID should be reasonable length"
