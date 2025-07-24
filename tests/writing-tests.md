# Testing Guidelines for mxgo

## Core Principles

### 1. Minimal Mocking
- **Mock only external dependencies**: Mock only what you absolutely need to control (external APIs, email sending, Redis, database when needed)
- **Prefer real implementations**: Let the actual business logic run to catch real bugs
- **Example**: In `test_process_email_task_happy_path_with_attachment`, only `EmailSender.send_reply` is mocked - everything else runs actual code

### 2. Reuse Assertion Code
- **Create helper assertion functions**: Use functions like `_assert_basic_successful_processing()` to avoid duplicating assertion logic
- **Build reusable fixtures**: Use parameterized fixtures like `prepare_email_request_data()` to create test data consistently
- **Extract common validation**: Functions like `validate_send_task()` and `assert_successful_response()` prevent repetitive assertion code

## Test Structure Patterns

### 3. Fixture Organization
```python
# Use factory fixtures for flexible test data creation
@pytest.fixture
def prepare_email_request_data(tmp_path):
    def _prepare(to_email="ask@mxgo.com", from_email="test@example.com", ...):
        # Setup logic here
        return email_data, attachments_dir, attachment_info
    return _prepare

# Create mock objects consistently
def create_mock_task(self, task_id: str, status: TaskStatus = TaskStatus.ACTIVE):
    mock_task = Mock()
    # Standard mock setup
    return mock_task
```

### 4. Test Data Management
- **Use `tmp_path` for file operations**: Always use pytest's `tmp_path` fixture for temporary files/directories
- **Clean up resources**: Verify cleanup happens (e.g., `attachments_cleaned_up_dir` assertions)
- **Use realistic test data**: Create meaningful test content that reflects actual usage

### 5. Database Testing
- **Session-scoped database setup**: Use `conftest.py` for database initialization with proper migration handling
- **Clean between tests**: Use `clean_database` fixture to truncate tables between tests
- **Mock database when appropriate**: Mock database operations for isolation when testing business logic

## Specific Testing Patterns

### 6. API Testing
```python
# Use dedicated test client with proper setup
@pytest.fixture
def client_with_patched_redis():
    fake_redis_instance = FakeAsyncRedis()
    with TestClient(app) as test_client:
        # Setup mocks and yield test_client

# Reusable request helpers
def make_post_request_with_client(test_client, form_data, endpoint, files=None):
    # Standard request setup
    return test_client.post(endpoint, data=form_data, files=files, headers=headers)
```

### 7. Async Code Testing
```python
# Mock async functions properly
async def mock_async_send_reply(*args, **kwargs):
    return {"MessageId": "mocked_id", "status": "sent"}

mock_sender_instance.send_reply = MagicMock(side_effect=mock_async_send_reply)
```

### 8. Time-Dependent Testing
```python
# Use freezegun for time control
@freeze_time("2024-01-15 10:00:00 UTC")
def test_time_sensitive_functionality():
    # Test logic here
```

## Test Organization

### 9. Test Class Structure
```python
class TestFeatureName:
    """Test the feature functionality."""

    def create_mock_helper(self, ...):
        """Helper to create consistent mock objects."""

    def test_happy_path(self):
        """Test the main success scenario."""

    def test_edge_cases(self):
        """Test boundary conditions."""

    def test_error_handling(self):
        """Test error scenarios."""
```

### 10. Test Naming
- **Descriptive names**: `test_process_email_task_happy_path_with_attachment`
- **Include context**: `test_task_execution_before_start_time`
- **Specify scenario**: `test_email_hourly_rate_limit_exceeded`

### 11. Assertion Patterns
```python
# Use specific assertions
assert isinstance(result, DetailedEmailProcessingResult), "Return type mismatch"
assert result.metadata.mode == expected_handle, f"Expected {expected_handle}, got {result.metadata.mode}"

# Check for absence of errors
assert not result.metadata.errors, f"Expected no errors, but got: {result.metadata.errors}"

# Verify cleanup
assert not Path(attachments_dir).exists(), f"Directory '{attachments_dir}' was not cleaned up"
```

## Best Practices

### 12. Error Testing
- **Test exception scenarios**: Use `pytest.raises()` for expected exceptions
- **Verify error messages**: Check that error messages are meaningful
- **Test error recovery**: Ensure system handles errors gracefully

### 13. Parameterized Testing
```python
@pytest.mark.parametrize("handle_instructions", DEFAULT_EMAIL_HANDLES)
def test_process_email_task_for_handle(handle_instructions, prepare_email_request_data):
    # Test all email handles with same logic
```

### 14. Integration vs Unit Testing
- **Integration tests**: Test complete workflows (like `process_email_task`) with minimal mocking
- **Unit tests**: Test individual components (like `ReportFormatter`) in isolation
- **Use real dependencies when possible**: Database connections, file operations, business logic

### 15. Mock Verification
```python
# Verify mocks were called correctly
mock_sender_instance.send_reply.assert_called_once()
call_args = mock_sender_instance.send_reply.call_args
assert call_args[0][0]["from"] == expected_email
```

## Anti-Patterns to Avoid

### 16. What NOT to Do
- ❌ **Over-mocking**: Don't mock internal business logic unless absolutely necessary
- ❌ **Brittle assertions**: Avoid asserting on internal implementation details
- ❌ **Copy-paste tests**: Don't duplicate assertion logic across tests
- ❌ **Magic values**: Use constants and descriptive variable names
- ❌ **Testing implementation**: Test behavior, not internal code structure
- ❌ **Ignoring cleanup**: Always verify resources are properly cleaned up

## Test File Organization

### 17. File Structure
```
tests/
├── conftest.py              # Shared fixtures and database setup
├── test_process_email.py    # Main email processing tests
├── test_api.py              # API endpoint tests
├── test_scheduled_tasks.py  # Scheduled task functionality
└── test_report_formatter.py # Individual component tests
```

### 18. Import Organization

```python
# Standard library imports first
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Third-party imports
import pytest

# Local imports
from mxgo.schemas import DetailedEmailProcessingResult
from mxgo.tasks import process_email_task
```

These guidelines ensure tests are maintainable, reliable, and provide good coverage while minimizing fragility through excessive mocking.
