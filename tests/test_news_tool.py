import json
import os
from unittest.mock import Mock, patch

import pytest
import requests

from mxgo.request_context import RequestContext
from mxgo.schemas import EmailRequest
from mxgo.tools.news_tool import NewsTool


# Helper function to create mock context
def create_mock_context():
    email_request = EmailRequest(
        from_email="test@example.com", to="recipient@example.com", subject="Test Subject", textContent="Test content"
    )
    return RequestContext(email_request)


def parse_tool_output(result):
    """Parse tool output JSON and return content."""
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
            return parsed.get("content", result)
        except json.JSONDecodeError:
            return result
    return result


class TestNewsTool:
    """Test the NewsTool core functionality."""

    def test_initialization_without_api_key(self):
        """Test NewsTool initialization without API key."""
        with patch.dict(os.environ, {}, clear=True):
            context = create_mock_context()
            tool = NewsTool(context)

            assert tool.api_key is None
            assert tool.name == "news_search"
            assert "search for current news" in tool.description.lower()
            assert "brave search news api" in tool.description.lower()

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    def test_initialization_with_api_key(self):
        """Test NewsTool initialization with API key."""
        context = create_mock_context()
        tool = NewsTool(context)

        assert tool.api_key == "test_api_key"

    def test_tool_interface_compliance(self):
        """Test that NewsTool complies with Tool interface."""
        context = create_mock_context()
        tool = NewsTool(context)

        assert hasattr(tool, "name")
        assert hasattr(tool, "description")
        assert hasattr(tool, "inputs")
        assert hasattr(tool, "output_type")
        assert hasattr(tool, "forward")

        # Check input schema
        assert "query" in tool.inputs
        assert tool.inputs["query"]["type"] == "string"
        assert tool.inputs["query"]["description"]

        # Check optional parameters
        assert "freshness" in tool.inputs
        assert "country" in tool.inputs
        assert "search_lang" in tool.inputs
        assert "count" in tool.inputs

        assert tool.output_type == "object"

    def test_forward_without_api_key_raises_error(self):
        """Test that forward raises error when no API key is configured."""
        with patch.dict(os.environ, {}, clear=True):
            context = create_mock_context()
            tool = NewsTool(context)

            with pytest.raises(ValueError, match="Brave Search API key not configured"):
                tool.forward("test query")

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    @patch("requests.get")
    def test_forward_success(self, mock_get):
        """Test successful news search execution."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "results": [
                {
                    "title": "Breaking News: Test Story 1",
                    "url": "https://news1.com/story1",
                    "description": "First test news story description",
                    "published": "2024-01-15T10:30:00Z",
                    "source": {"name": "Test News 1"},
                },
                {
                    "title": "Latest Update: Test Story 2",
                    "url": "https://news2.com/story2",
                    "description": "Second test news story description",
                    "published": "2024-01-15T09:15:00Z",
                    "source": {"name": "Test News 2"},
                },
            ]
        }
        mock_get.return_value = mock_response

        context = create_mock_context()
        tool = NewsTool(context)
        result = tool.forward("test news query")

        # Parse JSON output and check content contains news results
        content = parse_tool_output(result)
        assert "Breaking News: Test Story 1" in content
        assert "https://news1.com/story1" in content
        assert "First test news story description" in content
        assert "Latest Update: Test Story 2" in content

        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == "https://api.search.brave.com/res/v1/news/search"
        assert call_args[1]["headers"]["X-Subscription-Token"] == "test_api_key"
        assert call_args[1]["params"]["q"] == "test news query"

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    @patch("requests.get")
    def test_forward_with_custom_parameters(self, mock_get):
        """Test news search with custom parameters."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"results": []}
        mock_get.return_value = mock_response

        context = create_mock_context()
        tool = NewsTool(context)
        tool.forward(
            query="test query",
            freshness="pd",  # past day
            country="GB",
            search_lang="en",
            count=10,
        )

        call_params = mock_get.call_args[1]["params"]
        assert call_params["q"] == "test query"
        assert call_params["freshness"] == "pd"
        assert call_params["country"] == "GB"
        assert call_params["search_lang"] == "en"
        assert call_params["count"] == 10

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    @patch("requests.get")
    def test_forward_no_results(self, mock_get):
        """Test news search when no results are returned."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"results": []}
        mock_get.return_value = mock_response

        context = create_mock_context()
        tool = NewsTool(context)
        result = tool.forward("no results query")

        # Parse JSON output and check content
        content = parse_tool_output(result)
        assert "No news articles found for query: 'no results query'" in content

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    @patch("requests.get")
    def test_forward_http_error(self, mock_get):
        """Test news search HTTP error handling."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("API Error")
        mock_get.return_value = mock_response

        context = create_mock_context()
        tool = NewsTool(context)

        with pytest.raises(ValueError, match="News search request failed"):
            tool.forward("test query")

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    @patch("requests.get")
    def test_forward_request_exception(self, mock_get):
        """Test news search request exception handling."""
        mock_get.side_effect = requests.RequestException("Network error")

        context = create_mock_context()
        tool = NewsTool(context)

        with pytest.raises(ValueError, match="News search request failed"):
            tool.forward("test query")

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    @patch("requests.get")
    def test_api_integration(self, mock_get):
        """Test that API integration works correctly with all required headers and params."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "results": [
                {"title": "API Integration Test", "url": "https://test.com", "description": "Testing API integration"}
            ]
        }
        mock_get.return_value = mock_response

        context = create_mock_context()
        tool = NewsTool(context)
        result = tool.forward("api test")

        # Verify API call structure
        mock_get.assert_called_once()
        call_args = mock_get.call_args

        # Check URL
        assert call_args[0][0] == "https://api.search.brave.com/res/v1/news/search"

        # Check headers
        headers = call_args[1]["headers"]
        assert "X-Subscription-Token" in headers
        assert headers["Accept"] == "application/json"
        assert headers["Accept-Encoding"] == "gzip"

        # Check params
        params = call_args[1]["params"]
        assert params["q"] == "api test"
        assert "count" in params
        assert "country" in params
        assert "search_lang" in params
        assert "freshness" in params
        assert "spellcheck" in params

        # Verify result contains expected data
        content = parse_tool_output(result)
        assert "API Integration Test" in content

    def test_input_validation_schema(self):
        """Test that input validation schema is properly defined."""
        context = create_mock_context()
        tool = NewsTool(context)

        # Check that validation dict exists
        assert hasattr(tool, "inputs")
        validation_dict = tool.inputs

        # Check required query parameter
        assert "query" in validation_dict
        query_spec = validation_dict["query"]
        assert query_spec["type"] == "string"

        # Check optional parameters with proper types
        optional_params = ["freshness", "country", "search_lang", "count"]
        for param in optional_params:
            assert param in validation_dict
            param_spec = validation_dict[param]
            assert param_spec["type"] in ["string", "integer"]
