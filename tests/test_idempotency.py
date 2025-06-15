from unittest.mock import AsyncMock, patch

from mxtoai.email_sender import generate_message_id


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
            files_count=2
        )

        msg_id_2 = generate_message_id(
            from_email="test@example.com",
            to="ask@mxtoai.com",
            subject="Test Subject",
            date="2023-01-01T12:00:00Z",
            html_content="<p>Test HTML</p>",
            text_content="Test text",
            files_count=2
        )

        assert msg_id_1 == msg_id_2, "Same inputs should produce same message ID"
        assert msg_id_1.startswith("<") and msg_id_1.endswith("@mxtoai.com>"), "Should be in email format"

        # Test with different inputs
        msg_id_3 = generate_message_id(
            from_email="different@example.com",  # Changed
            to="ask@mxtoai.com",
            subject="Test Subject",
            date="2023-01-01T12:00:00Z",
            html_content="<p>Test HTML</p>",
            text_content="Test text",
            files_count=2
        )

        assert msg_id_1 != msg_id_3, "Different inputs should produce different message IDs"

    @patch("mxtoai.validators.redis_client")
    @patch("mxtoai.api.process_email_task")
    async def test_api_idempotency_already_queued(self, mock_task, mock_redis):
        """Test API returns conflict when email already queued."""
        from fastapi.testclient import TestClient

        from mxtoai.api import app

        # Setup mock Redis client
        mock_redis.get = AsyncMock(return_value="1")  # Already queued

        client = TestClient(app)

        form_data = {
            "from_email": "test@example.com",
            "to": "ask@mxtoai.com",
            "subject": "Test Subject",
            "textContent": "Test content",
            "messageId": "<test123@example.com>",
        }

        response = client.post(
            "/process-email",
            data=form_data,
            headers={"x-api-key": "test-key"}
        )

        assert response.status_code == 409
        response_data = response.json()
        assert response_data["status"] == "duplicate_queued"
        assert "already queued" in response_data["message"]

        # Task should not be called
        mock_task.send.assert_not_called()

    @patch("mxtoai.validators.redis_client")
    @patch("mxtoai.api.process_email_task")
    async def test_api_idempotency_already_processed(self, mock_task, mock_redis):
        """Test API returns conflict when email already processed."""
        from fastapi.testclient import TestClient

        from mxtoai.api import app

        # Setup mock Redis client - not queued but already processed
        mock_redis.get = AsyncMock(side_effect=lambda key: "1" if "processed" in key else None)

        client = TestClient(app)

        form_data = {
            "from_email": "test@example.com",
            "to": "ask@mxtoai.com",
            "subject": "Test Subject",
            "textContent": "Test content",
            "messageId": "<test123@example.com>",
        }

        response = client.post(
            "/process-email",
            data=form_data,
            headers={"x-api-key": "test-key"}
        )

        assert response.status_code == 409
        response_data = response.json()
        assert response_data["status"] == "duplicate_processed"
        assert "already processed" in response_data["message"]

        # Task should not be called
        mock_task.send.assert_not_called()

    @patch("mxtoai.validators.check_task_idempotency")
    def test_task_idempotency_already_processed(self, mock_check_idempotency):
        """Test task returns early when email already processed."""
        from mxtoai.tasks import process_email_task
        
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
            "attachments": []
        }

        result = process_email_task(
            email_data=email_data,
            email_attachments_dir="",
            attachment_info=[],
            scheduled_task_id=None
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
            files_count=0
        )

        msg_id_2 = generate_message_id(
            from_email="test@example.com",
            to="ask@mxtoai.com",
            subject="Test Subject",
            date="2023-01-01T12:00:00Z",
            html_content="<p>Test HTML</p>",
            text_content="Test text",
            files_count=0
        )

        assert msg_id_1 == msg_id_2, "Should generate same ID for same content"
        assert len(msg_id_1) > 10, "Generated ID should be reasonable length"
