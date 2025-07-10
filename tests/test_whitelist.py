import os
import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest

import mxtoai.whitelist
from mxtoai.whitelist import (
    get_whitelist_signup_url,
    init_supabase,
    is_email_whitelisted,
    send_verification_email,
    trigger_automatic_verification,
)


class TestSupabaseInitialization:
    """Test Supabase client initialization."""

    @patch.dict(os.environ, {"SUPABASE_URL": "https://test.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "test_key"})
    @patch("mxtoai.whitelist.create_client")
    def test_init_supabase_success(self, mock_create_client):
        """Test successful Supabase initialization."""
        mock_client = Mock()
        mock_create_client.return_value = mock_client

        # Reset global state
        mxtoai.whitelist.supabase = None

        init_supabase()

        mock_create_client.assert_called_once_with(supabase_url="https://test.supabase.co", supabase_key="test_key")
        assert mxtoai.whitelist.supabase == mock_client

    @patch.dict(os.environ, {}, clear=True)
    def test_init_supabase_missing_env_vars(self):
        """Test Supabase initialization with missing environment variables."""
        # Reset global state
        mxtoai.whitelist.supabase = None

        with pytest.raises(ValueError, match="Supabase URL and service role key must be set"):
            init_supabase()

    @patch.dict(os.environ, {"SUPABASE_URL": "https://test.supabase.co"}, clear=True)
    def test_init_supabase_missing_key(self):
        """Test Supabase initialization with missing service role key."""
        # Reset global state
        mxtoai.whitelist.supabase = None

        with pytest.raises(ValueError, match="Supabase URL and service role key must be set"):
            init_supabase()

    @patch.dict(os.environ, {"SUPABASE_URL": "https://test.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "test_key"})
    @patch("mxtoai.whitelist.create_client")
    def test_init_supabase_client_creation_error(self, mock_create_client):
        """Test Supabase initialization with client creation error."""
        mock_create_client.side_effect = Exception("Connection failed")

        # Reset global state
        mxtoai.whitelist.supabase = None

        with pytest.raises(Exception, match="Connection failed"):
            init_supabase()

    @patch.dict(os.environ, {"SUPABASE_URL": "https://test.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "test_key"})
    @patch("mxtoai.whitelist.create_client")
    def test_init_supabase_already_initialized(self, mock_create_client):
        """Test that initialization is skipped when client already exists."""
        existing_client = Mock()
        mxtoai.whitelist.supabase = existing_client

        init_supabase()

        # Should not create new client
        mock_create_client.assert_not_called()
        assert mxtoai.whitelist.supabase == existing_client


class TestEmailWhitelistCheck:
    """Test email whitelist checking functionality."""

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"WHITELIST_ENABLED": "true"})
    async def test_is_email_whitelisted_exists_verified(self):
        """Test email that exists and is verified."""
        mock_supabase = Mock()
        mock_response = Mock()
        mock_response.data = [{"email": "test@example.com", "verified": True}]
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_response
        mock_supabase.table.return_value = mock_table

        with patch("mxtoai.whitelist.supabase", mock_supabase):
            exists, verified = await is_email_whitelisted("test@example.com")

        assert exists is True
        assert verified is True
        mock_supabase.table.assert_called_once_with("whitelisted_emails")
        mock_table.select.assert_called_once_with("*")

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"WHITELIST_ENABLED": "true"})
    async def test_is_email_whitelisted_exists_not_verified(self):
        """Test email that exists but is not verified."""
        mock_supabase = Mock()
        mock_response = Mock()
        mock_response.data = [{"email": "test@example.com", "verified": False}]
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_response
        mock_supabase.table.return_value = mock_table

        with patch("mxtoai.whitelist.supabase", mock_supabase):
            exists, verified = await is_email_whitelisted("test@example.com")

        assert exists is True
        assert verified is False

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"WHITELIST_ENABLED": "true"})
    async def test_is_email_whitelisted_not_exists(self):
        """Test email that does not exist in whitelist."""
        mock_supabase = Mock()
        mock_response = Mock()
        mock_response.data = []
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_response
        mock_supabase.table.return_value = mock_table

        with patch("mxtoai.whitelist.supabase", mock_supabase):
            exists, verified = await is_email_whitelisted("nonexistent@example.com")

        assert exists is False
        assert verified is False

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"WHITELIST_ENABLED": "true"})
    async def test_is_email_whitelisted_supabase_not_initialized(self):
        """Test email whitelist check when Supabase is not initialized."""
        with patch("mxtoai.whitelist.supabase", None), patch("mxtoai.whitelist.init_supabase") as mock_init:
            mock_supabase = Mock()
            mock_response = Mock()
            mock_response.data = [{"email": "test@example.com", "verified": True}]
            mock_table = Mock()
            mock_table.select.return_value.eq.return_value.execute.return_value = mock_response
            mock_supabase.table.return_value = mock_table

            # Mock init_supabase to set the client
            def set_supabase():
                mxtoai.whitelist.supabase = mock_supabase

            mock_init.side_effect = set_supabase

            exists, verified = await is_email_whitelisted("test@example.com")

        assert exists is True
        assert verified is True
        mock_init.assert_called_once()

    @pytest.mark.asyncio
    @patch.dict(os.environ, {"WHITELIST_ENABLED": "true"})
    async def test_is_email_whitelisted_database_error(self):
        """Test email whitelist check with database error."""
        mock_supabase = Mock()
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.execute.side_effect = Exception("Database error")
        mock_supabase.table.return_value = mock_table

        with patch("mxtoai.whitelist.supabase", mock_supabase):
            exists, verified = await is_email_whitelisted("test@example.com")

        assert exists is False
        assert verified is False


class TestAutomaticVerification:
    """Test automatic email verification functionality."""

    @pytest.mark.asyncio
    async def test_trigger_automatic_verification_new_email(self):
        """Test triggering verification for a new email."""
        mock_supabase = Mock()

        # Mock existing email check (returns empty)
        existing_response = Mock()
        existing_response.data = []
        existing_table = Mock()
        existing_table.select.return_value.eq.return_value.execute.return_value = existing_response

        # Mock insert operation
        insert_response = Mock()
        insert_response.data = [{"email": "new@example.com", "verified": False}]
        insert_table = Mock()
        insert_table.insert.return_value.execute.return_value = insert_response

        mock_supabase.table.side_effect = [existing_table, insert_table]

        with (
            patch("mxtoai.whitelist.supabase", mock_supabase),
            patch("mxtoai.whitelist.send_verification_email", return_value=True) as mock_send,
        ):
            result = await trigger_automatic_verification("new@example.com")

        assert result is True
        mock_send.assert_called_once()
        # Check that insert was called with correct structure
        insert_call_args = insert_table.insert.call_args[0][0]
        assert insert_call_args["email"] == "new@example.com"
        assert insert_call_args["verified"] is False
        assert "verification_token" in insert_call_args

    @pytest.mark.asyncio
    async def test_trigger_automatic_verification_existing_email(self):
        """Test triggering verification for an existing email."""
        mock_supabase = Mock()

        # Mock existing email check (returns email)
        existing_response = Mock()
        existing_response.data = [{"email": "existing@example.com", "verified": False}]
        existing_table = Mock()
        existing_table.select.return_value.eq.return_value.execute.return_value = existing_response

        # Mock update operation
        update_response = Mock()
        update_response.data = [{"email": "existing@example.com", "verified": False}]
        update_table = Mock()
        update_table.update.return_value.eq.return_value.execute.return_value = update_response

        mock_supabase.table.side_effect = [existing_table, update_table]

        with (
            patch("mxtoai.whitelist.supabase", mock_supabase),
            patch("mxtoai.whitelist.send_verification_email", return_value=True) as mock_send,
        ):
            result = await trigger_automatic_verification("existing@example.com")

        assert result is True
        mock_send.assert_called_once()
        # Check that update was called
        update_call_args = update_table.update.call_args[0][0]
        assert update_call_args["verified"] is False
        assert "verification_token" in update_call_args

    @pytest.mark.asyncio
    async def test_trigger_automatic_verification_send_email_fails(self):
        """Test verification trigger when email sending fails."""
        mock_supabase = Mock()
        existing_response = Mock()
        existing_response.data = []
        existing_table = Mock()
        existing_table.select.return_value.eq.return_value.execute.return_value = existing_response

        insert_response = Mock()
        insert_response.data = [{"email": "test@example.com"}]
        insert_table = Mock()
        insert_table.insert.return_value.execute.return_value = insert_response

        mock_supabase.table.side_effect = [existing_table, insert_table]

        with (
            patch("mxtoai.whitelist.supabase", mock_supabase),
            patch("mxtoai.whitelist.send_verification_email", return_value=False),
        ):
            result = await trigger_automatic_verification("test@example.com")

        assert result is False

    @pytest.mark.asyncio
    async def test_trigger_automatic_verification_database_error(self):
        """Test verification trigger with database error."""
        mock_supabase = Mock()
        mock_table = Mock()
        mock_table.select.return_value.eq.return_value.execute.side_effect = Exception("DB error")
        mock_supabase.table.return_value = mock_table

        with patch("mxtoai.whitelist.supabase", mock_supabase):
            result = await trigger_automatic_verification("test@example.com")

        assert result is False


class TestSendVerificationEmail:
    """Test verification email sending functionality."""

    @pytest.mark.asyncio
    async def test_send_verification_email_success(self):
        """Test successful verification email sending."""
        mock_email_sender = Mock()
        mock_email_sender.return_value.send_email = AsyncMock(return_value={"MessageId": "test-123"})

        with (
            patch("mxtoai.email_sender.EmailSender", mock_email_sender),
            patch.dict(os.environ, {"FRONTEND_URL": "https://test.mxtoai.com"}),
        ):
            result = await send_verification_email("test@example.com", "token-123")

        assert result is True
        mock_email_sender.assert_called_once()
        mock_email_sender.return_value.send_email.assert_called_once()

        # Check email content
        call_args = mock_email_sender.return_value.send_email.call_args
        assert call_args.kwargs["to_address"] == "test@example.com"
        assert "Verify your email" in call_args.kwargs["subject"]
        assert "https://test.mxtoai.com/verify?token=token-123" in call_args.kwargs["body_text"]

    @pytest.mark.asyncio
    async def test_send_verification_email_default_url(self):
        """Test verification email with default frontend URL."""
        mock_email_sender = Mock()
        mock_email_sender.return_value.send_email = AsyncMock(return_value={"MessageId": "test-123"})

        with patch("mxtoai.email_sender.EmailSender", mock_email_sender), patch.dict(os.environ, {}, clear=True):
            result = await send_verification_email("test@example.com", "token-456")

        assert result is True
        call_args = mock_email_sender.return_value.send_email.call_args
        assert "https://mxtoai.com/verify?token=token-456" in call_args.kwargs["body_text"]

    @pytest.mark.asyncio
    async def test_send_verification_email_failure(self):
        """Test verification email sending failure."""
        mock_email_sender = Mock()
        mock_email_sender.return_value.send_email = AsyncMock(side_effect=Exception("Send failed"))

        with patch("mxtoai.email_sender.EmailSender", mock_email_sender):
            result = await send_verification_email("test@example.com", "token-789")

        assert result is False

    @pytest.mark.asyncio
    async def test_send_verification_email_html_content(self):
        """Test that verification email includes proper HTML content."""
        mock_email_sender = Mock()
        mock_email_sender.return_value.send_email = AsyncMock(return_value={"MessageId": "test-123"})

        with patch("mxtoai.email_sender.EmailSender", mock_email_sender):
            await send_verification_email("test@example.com", "token-html")

        call_args = mock_email_sender.return_value.send_email.call_args
        html_content = call_args.kwargs["body_html"]

        assert "<!DOCTYPE html>" in html_content
        assert "Welcome to MXtoAI!" in html_content
        assert "token-html" in html_content
        assert "verify?token=" in html_content


class TestWhitelistSignupUrl:
    """Test whitelist signup URL generation."""

    @patch.dict(os.environ, {"WHITELIST_SIGNUP_URL": "https://custom.mxtoai.com/waitlist"})
    def test_get_whitelist_signup_url_custom(self):
        """Test signup URL with custom whitelist signup URL."""
        url = get_whitelist_signup_url()
        assert url == "https://custom.mxtoai.com/waitlist"

    @patch.dict(os.environ, {}, clear=True)
    def test_get_whitelist_signup_url_default(self):
        """Test signup URL with default whitelist signup URL."""
        url = get_whitelist_signup_url()
        assert url == "https://mxtoai.com/whitelist"


class TestIntegrationScenarios:
    """Test integrated workflow scenarios."""

    @pytest.mark.asyncio
    async def test_full_verification_workflow_new_user(self):
        """Test complete verification workflow for new user."""
        mock_supabase = Mock()

        # First call: check existing (empty)
        existing_response = Mock()
        existing_response.data = []
        existing_table = Mock()
        existing_table.select.return_value.eq.return_value.execute.return_value = existing_response

        # Second call: insert new record
        insert_response = Mock()
        insert_response.data = [{"email": "newuser@example.com", "verified": False}]
        insert_table = Mock()
        insert_table.insert.return_value.execute.return_value = insert_response

        mock_supabase.table.side_effect = [existing_table, insert_table]

        mock_email_sender = Mock()
        mock_email_sender.return_value.send_email = AsyncMock(return_value={"MessageId": "msg-123"})

        with (
            patch("mxtoai.whitelist.supabase", mock_supabase),
            patch("mxtoai.email_sender.EmailSender", mock_email_sender),
        ):
            # Trigger verification
            verification_result = await trigger_automatic_verification("newuser@example.com")

            # Check whitelist status
            exists, verified = await is_email_whitelisted("newuser@example.com")

        assert verification_result is True
        # Note: In real scenario, this would depend on the actual database state
        # Here we're testing the function behavior independently

    @pytest.mark.asyncio
    async def test_uuid_generation_uniqueness(self):
        """Test that verification tokens are unique."""
        with patch("mxtoai.whitelist.uuid.uuid4") as mock_uuid:
            mock_uuid.side_effect = [
                Mock(spec=uuid.UUID, __str__=lambda self: "token-1"),
                Mock(spec=uuid.UUID, __str__=lambda self: "token-2"),
            ]

            mock_supabase = Mock()
            existing_response = Mock()
            existing_response.data = []
            mock_table = Mock()
            mock_table.select.return_value.eq.return_value.execute.return_value = existing_response
            insert_response = Mock()
            insert_response.data = [{"email": "test@example.com"}]
            mock_table.insert.return_value.execute.return_value = insert_response
            mock_supabase.table.return_value = mock_table

            with (
                patch("mxtoai.whitelist.supabase", mock_supabase),
                patch("mxtoai.whitelist.send_verification_email", return_value=True),
            ):
                await trigger_automatic_verification("user1@example.com")
                await trigger_automatic_verification("user2@example.com")

        # Verify uuid.uuid4 was called twice
        assert mock_uuid.call_count == 2
