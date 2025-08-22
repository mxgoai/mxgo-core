import re
from unittest.mock import Mock, patch

import pytest

from mxgo._logging import (
    COMPILED_PATTERNS,
    SENSITIVE_PATTERNS,
    get_smolagents_console,
    loguru_scrubbing_filter,
    scrub_sensitive_data,
)


class TestSensitiveDataScrubbing:
    """Test the sensitive data scrubbing functionality."""

    def test_scrub_basic_password_pattern(self):
        """Test scrubbing of basic password patterns."""
        test_cases = [
            ("password=secret123", "password=[******]"),
            ("PASSWORD=secret123", "PASSWORD=[******]"),
            ("user_password=mypass", "user_password=[******]"),
            ('"password": "secret123"', '"password": "[******]"'),
            ("'passwd': 'secret123'", "'passwd': '[******]'"),
        ]

        for input_text, _expected in test_cases:
            result = scrub_sensitive_data(input_text)
            assert "******" in result, f"Expected scrubbing in: {input_text}"

    def test_scrub_email_patterns(self):
        """Test scrubbing of email-related sensitive data."""
        test_cases = [
            "email=user@example.com",
            "EMAIL=user@example.com",
            "e-mail=user@example.com",
            "user_email=test@domain.com",
            '"email": "user@example.com"',
            "mail_address=someone@test.org",
        ]

        for input_text in test_cases:
            result = scrub_sensitive_data(input_text)
            assert "******" in result, f"Expected scrubbing in: {input_text}"

    def test_scrub_api_keys_and_tokens(self):
        """Test scrubbing of API keys and authentication tokens."""
        test_cases = [
            "api_key=abc123xyz",
            "api-key=secret",
            "private_key=rsa_key_data",
            "bearer_token=jwt_token_here",
            "jwt=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9",
            "session_id=session123",
            "csrf_token=csrf123",
        ]

        for input_text in test_cases:
            result = scrub_sensitive_data(input_text)
            assert "******" in result, f"Expected scrubbing in: {input_text}"

    def test_case_insensitive_matching(self):
        """Test that pattern matching is case-insensitive."""
        test_cases = [
            "PASSWORD=secret",
            "Password=secret",
            "password=secret",
            "EMAIL=user@test.com",
            "Email=user@test.com",
            "email=user@test.com",
        ]

        for input_text in test_cases:
            result = scrub_sensitive_data(input_text)
            assert "******" in result, f"Case-insensitive matching failed for: {input_text}"

    def test_non_string_input_handling(self):
        """Test handling of non-string inputs."""
        test_cases = [123, None, {"password": "secret"}, ["email=test@example.com"]]

        for input_value in test_cases:
            result = scrub_sensitive_data(input_value)
            assert isinstance(result, str), f"Expected string output for input: {input_value}"

    def test_safe_text_not_scrubbed(self):
        """Test that safe text without sensitive patterns is not ******."""
        safe_texts = [
            "This is a normal log message",
            "User logged in successfully",
            "Processing email request",  # "email" alone without key=value pattern should be safe
            "Database connection established",
            "authentic user verified",  # Contains "auth" but not in key=value pattern
            "User has valid email address",  # "email" in context, not as key
            "Password authentication successful",  # "password" in context, not as key
        ]

        for safe_text in safe_texts:
            result = scrub_sensitive_data(safe_text)
            assert "******" not in result, f"Safe text was incorrectly ******: {safe_text}"
            assert result == safe_text, f"Safe text was modified: {safe_text} -> {result}"


class TestLoguruScrubbingFilter:
    """Test the Loguru scrubbing filter functionality."""

    def create_mock_record(self, message: str, extra_data: dict | None = None):
        """Helper to create mock loguru record objects."""
        return {"message": message, "extra": extra_data or {}}

    def test_filter_scrubs_message(self):
        """Test that the filter scrubs sensitive data from log messages."""
        test_cases = [
            "user_password=secret123",
            "email=user@example.com",
            "api_key=abc123xyz",
            "Processing credit_card=4111111111111111",
        ]

        for message in test_cases:
            record = self.create_mock_record(message)
            result = loguru_scrubbing_filter(record)

            assert result is True, "Filter should always return True"
            assert "******" in record["message"], f"Message not ******: {record['message']}"

    def test_filter_scrubs_extra_data(self):
        """Test that the filter scrubs sensitive data from extra fields."""
        extra_data = {
            "user_email": "test@example.com",
            "password": "secret123",
            "safe_field": "normal_value",
            "api_key": "sensitive_key_data",
        }

        record = self.create_mock_record("Test message", extra_data)
        result = loguru_scrubbing_filter(record)

        assert result is True, "Filter should always return True"
        assert record["extra"]["safe_field"] == "normal_value", "Safe field should not be modified"

        # Check that sensitive fields were ******
        sensitive_fields = ["user_email", "password", "api_key"]
        for field in sensitive_fields:
            assert "******" in str(record["extra"][field]), f"Extra field '{field}' not ******"

    def test_filter_handles_missing_attributes(self):
        """Test that the filter gracefully handles records missing expected attributes."""
        # Record with no message
        record_no_message = {"extra": {}}
        result = loguru_scrubbing_filter(record_no_message)
        assert result is True, "Filter should handle missing message"

        # Record with no extra
        record_no_extra = {"message": "test message"}
        result = loguru_scrubbing_filter(record_no_extra)
        assert result is True, "Filter should handle missing extra"

    def test_filter_error_handling(self):
        """Test that the filter handles errors gracefully without breaking logging."""
        # Create a problematic record that might cause errors
        problematic_record = {
            "message": "test message",
            "extra": {
                "bad_data": object()  # Non-serializable object
            },
        }

        # Should not raise an exception
        result = loguru_scrubbing_filter(problematic_record)
        assert result is True, "Filter should handle errors gracefully"


class TestRichConsoleScrubbing:
    """Test the Rich console scrubbing integration."""

    @patch("mxgo._logging.scrub_sensitive_data")
    def test_rich_console_applies_scrubbing(self, mock_scrub):
        """Test that Rich console output is ****** before logging."""
        mock_scrub.return_value = "****** content"

        console = get_smolagents_console()

        # Mock the terminal console to avoid actual output
        console.terminal_console = Mock()
        console.rich_logger = Mock()

        test_content = "password=secret123"
        console.print(test_content)

        # Verify scrubbing was called
        mock_scrub.assert_called_once_with(test_content)

        # Verify the ****** content was logged
        console.rich_logger.log.assert_called_once()


class TestLoggingIntegration:
    """Test integration of scrubbing with actual logging setup."""

    def test_sensitive_patterns_coverage(self):
        """Test that all expected sensitive patterns are included."""
        expected_patterns = [
            "password",
            "passwd",
            "secret",
            "credential",
            "key",
            "session",
            "cookie",
            "csrf",
            "jwt",
            "ssn",
            "email",
            "mail",
            "bearer",
        ]

        # Check that our patterns include the expected ones
        pattern_strings = [p.pattern for p in COMPILED_PATTERNS]
        combined_patterns = "|".join(pattern_strings).lower()

        for expected in expected_patterns:
            assert expected in combined_patterns, f"Missing expected pattern: {expected}"

    def test_compiled_patterns_are_case_insensitive(self):
        """Test that all compiled patterns use case-insensitive matching."""
        for pattern in COMPILED_PATTERNS:
            assert pattern.flags & re.IGNORECASE, f"Pattern should be case-insensitive: {pattern.pattern}"

    @pytest.mark.parametrize("pattern_name", ["password", "email", "secret", "session"])
    def test_individual_pattern_matching(self, pattern_name):
        """Test that individual patterns work correctly."""
        test_strings = [
            f"{pattern_name}=sensitive_data",
            f"{pattern_name.upper()}=sensitive_data",
            f"user_{pattern_name}=sensitive_data",
        ]

        for test_string in test_strings:
            result = scrub_sensitive_data(test_string)
            assert "******" in result, f"Pattern '{pattern_name}' failed to match in: {test_string}"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_multiple_patterns_in_single_string(self):
        """Test scrubbing when multiple sensitive patterns exist in one string."""
        input_text = "user_email=test@example.com password=secret123 api_key=abc123"
        result = scrub_sensitive_data(input_text)

        # Should scrub sensitive data
        assert "******" in result, f"Expected scrubbing in: {result}"

    def test_empty_and_whitespace_handling(self):
        """Test handling of empty strings and whitespace."""
        test_cases = ["", "   ", "\n", "\t", "  \n  "]

        for input_text in test_cases:
            result = scrub_sensitive_data(input_text)
            assert result == input_text, f"Empty/whitespace text was modified: '{input_text}' -> '{result}'"

    def test_special_characters_in_sensitive_data(self):
        """Test handling of special characters in sensitive data."""
        test_cases = ["password=p@$$w0rd!", "email=user+tag@example.com", "api_key=abc-123_xyz.789"]

        for test_string in test_cases:
            result = scrub_sensitive_data(test_string)
            assert "******" in result, f"Failed to scrub: {test_string}"


class TestActualLoggingIntegration:
    """Test integration with actual logging setup."""

    def test_scrubbing_patterns_are_properly_configured(self):
        """Test that scrubbing patterns are properly configured in the logging system."""
        # Verify patterns are loaded
        assert len(SENSITIVE_PATTERNS) > 0, "No sensitive patterns configured"
        assert len(COMPILED_PATTERNS) > 0, "No compiled patterns available"

        # Test that our key patterns are included
        key_patterns = ["password", "email", "secret", "api", "key"]
        pattern_text = "|".join(SENSITIVE_PATTERNS).lower()

        for key_pattern in key_patterns:
            assert key_pattern in pattern_text, f"Missing key pattern: {key_pattern}"

        # Test scrubbing functionality works end-to-end
        test_data = "user_password=secret123 api_key=abc123 email=test@example.com"
        result = scrub_sensitive_data(test_data)

        assert "******" in result, "Scrubbing function not working"
        assert "secret123" not in result, "Password not ******"
        assert "abc123" not in result, "API key not ******"
        assert "test@example.com" not in result, "Email not ******"

    def test_logging_filter_integration(self):
        """Test that the logging filter is properly integrated."""
        # Create a test record with sensitive data
        test_record = {
            "message": "Login attempt with password=secret123",
            "extra": {"user_email": "test@example.com", "api_key": "sensitive_key", "safe_field": "normal_value"},
        }

        # Apply the filter
        result = loguru_scrubbing_filter(test_record)

        # Verify filter behavior
        assert result is True, "Filter should always return True"
        assert "******" in test_record["message"], "Message not ******"
        assert test_record["extra"]["user_email"] == "******", "Email field not ******"
        assert test_record["extra"]["api_key"] == "******", "API key field not ******"
        assert test_record["extra"]["safe_field"] == "normal_value", "Safe field should not be modified"
