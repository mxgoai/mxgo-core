# Guide to Adding New Tools in MxToAi

This guide outlines the process for adding new tools to the MxToAi email assistant. It covers architecture considerations, database integration, testing approaches, and best practices based on real implementation experience.

## 1. Tool Architecture Overview

MxToAi uses the `smolagents` framework for tool implementation, allowing the AI agent to access specialized functionality. Each tool should:

- Have a clear, single responsibility
- Be properly integrated with the agent's capabilities
- Handle errors gracefully
- Be thoroughly tested

### 1.1 Basic Tool Structure

```python
from smolagents import Tool

class YourNewTool(Tool):
    """
    Description of what your tool does.
    """

    def __init__(self, **kwargs):
        """Initialize tool with required dependencies."""
        super().__init__(**kwargs)

        # Initialize any required resources (DB connections, APIs, etc.)
        # ...

    def forward(self, *args, **kwargs):
        """
        Synchronous implementation of the tool's main functionality.

        Args:
            Arguments specific to your tool's functionality

        Returns:
            Dictionary with results or status information
        """
        # Implement the core functionality
        # ...

        return {"status": "success", "result": "..."}
```

## 2. Database Integration

### 2.1 Choosing Between Synchronous and Asynchronous Operations

For tools that interact with the database:

- **Prefer synchronous operations** for simpler implementation and compatibility with `smolagents`
- Use the `DbConnection` class for database access

```python
from mxtoai.db import init_db_connection

# Initialize at module level for reuse
db_connection = init_db_connection()

# In your tool:
def forward(self, ...):
    with db_connection.get_session() as session:
        # Perform database operations
        # ...
```

### 2.2 Handling Data Models

When working with database models:

- Consider potential circular imports
- Implement fallback mechanisms to handle different environments
- Support both ORM and raw SQL approaches when necessary

```python
# Example of a hybrid approach
try:
    # Try ORM approach first (good for testing)
    from mxtoai.models import YourModel

    model = YourModel(...)
    session.add(model)
    session.commit()

except (ImportError, Exception) as e:
    # Fall back to SQL approach if needed
    from sqlalchemy import text

    stmt = text("INSERT INTO your_table (column1, column2) VALUES (:val1, :val2)")
    session.execute(stmt, {"val1": value1, "val2": value2})
    session.commit()
```

## 3. Input Validation

Use Pydantic models to validate inputs to your tool:

```python
from pydantic import BaseModel, Field, field_validator

class ToolInput(BaseModel):
    """Input model for tool validation."""

    field1: str = Field(..., description="Description of field1")
    field2: int = Field(..., description="Description of field2")

    @field_validator("field1")
    @classmethod
    def validate_field1(cls, v):
        """Validate field1."""
        if not v:
            raise ValueError("field1 cannot be empty")
        return v
```

## 4. Error Handling and Logging

Implement robust error handling:

```python
from mxtoai.utils import get_logger

logger = get_logger(__name__)

def forward(self, ...):
    try:
        # Implementation
        logger.info("Operation successful: %s", details)
        return {"status": "success", "result": result}
    except Exception as e:
        error_message = f"Operation failed: {str(e)}"
        logger.error(error_message)
        return {"status": "error", "message": error_message}
```

## 5. Testing Strategy

### 5.1 Test Structure

Create comprehensive tests that cover:

1. Happy path scenarios
2. Error handling
3. Integration with the email agent
4. Edge cases

### 5.2 Mocking Dependencies

```python
# Example test with mocked dependencies
def test_your_tool(prepare_email_request_data):
    """Tests your tool functionality."""

    # Setup test data
    test_data = {...}

    # Create mock functions
    mock_resource = False
    mock_id = None

    def mock_db_function(data):
        nonlocal mock_resource, mock_id
        mock_resource = True
        mock_id = "test_id_123"

    # Apply mocks
    with (
        patch("module.path.to.dependency", side_effect=mock_db_function),
        patch("another.dependency"),
    ):
        # Execute function being tested
        result = your_function(test_data)

        # Verify behavior
        assert mock_resource, "Resource was not created"
        assert mock_id is not None, "ID was not generated"
        assert "success" in result, "Result should indicate success"
```

### 5.3 Testing Database Operations

When testing database operations:

- Mock both ORM methods (`Session.add`) and raw SQL methods (`Session.execute`)
- Create mock result objects that mimic the expected return values
- Test both approaches to ensure robustness

```python
def mock_session_execute(statement, params=None):
    """Mock for Session.execute."""
    # Record what would have been executed
    mock_executed = True

    # Create a mock result that mimics what execute() would return
    class MockResult:
        def scalar_one_or_none(self):
            return None

        def scalars(self):
            return self

        def first(self):
            return None

        def all(self):
            return []

    return MockResult()
```

## 6. Integration with Email Agent

Ensure your tool integrates properly with the email agent:

1. Import and register your tool in the appropriate location
2. Update the agent prompt if needed to describe your tool's capabilities
3. Ensure the tool works with the agent's execution flow

## 7. Best Practices

### 7.1 Code Organization

- Keep tool implementation in its own module in the `mxtoai/tools/` directory
- Use clear, descriptive names for classes and methods
- Document public APIs thoroughly with docstrings

### 7.2 Error Handling

- Validate inputs using Pydantic models
- Implement graceful error handling
- Return informative error messages
- Log errors at appropriate levels

### 7.3 Performance Considerations

- Round times to appropriate precision (e.g., minute-level for cron expressions)
- Implement caching for frequently accessed resources
- Use connection pooling for database operations

### 7.4 Testing

- Write tests for all key functionality
- Mock external dependencies
- Test both happy paths and error cases
- Include integration tests with the agent

## 8. Example: Adding a Scheduled Tasks Tool

Here's a simplified version of adding a scheduled tasks tool:

1. **Create the tool file** at `mxtoai/tools/scheduled_tasks_tool.py`
2. **Implement the tool class** with necessary functionality:
   - Input validation
   - Database operations
   - Error handling
   - Result formatting
3. **Write tests** in `tests/test_process_email.py`
   - Mock database operations
   - Test email handle integration
   - Verify task creation and storage
4. **Update agent configuration** to use the new tool
5. **Run tests** to verify proper integration

## 9. Troubleshooting Common Issues

- **Circular imports**: Use runtime imports or reorganize code structure
- **Async compatibility**: Make core functionality synchronous, provide async wrappers if needed
- **Test failures**: Ensure proper mocking of all dependencies
- **Database connection issues**: Verify connection setup and error handling
- **Agent integration**: Check tool registration and prompt configuration

## 10. Conclusion

Adding new tools to MxToAi requires careful planning, implementation, and testing. Following these guidelines will help ensure that your tool integrates smoothly with the existing system and provides reliable functionality.

Remember to:
- Keep the tool focused on a specific task
- Implement robust error handling
- Write comprehensive tests
- Document your code thoroughly
