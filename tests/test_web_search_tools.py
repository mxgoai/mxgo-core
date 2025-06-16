import os
from unittest.mock import Mock, patch

import pytest
import requests

from mxtoai.tools.web_search import BraveSearchTool, DDGSearchTool, GoogleSearchTool


class TestDDGSearchTool:
    """Test the DDGSearchTool functionality."""

    def test_initialization_default_max_results(self):
        """Test DDGSearchTool initialization with default parameters."""
        tool = DDGSearchTool()

        assert tool.max_results == 5
        assert tool.name == "ddg_search"
        assert "DuckDuckGo" in tool.description
        assert "cost-effective" in tool.description
        assert hasattr(tool, "ddg_tool")

    def test_initialization_custom_max_results(self):
        """Test DDGSearchTool initialization with custom max_results."""
        tool = DDGSearchTool(max_results=10)

        assert tool.max_results == 10

    def test_tool_interface_compliance(self):
        """Test that DDGSearchTool complies with Tool interface."""
        tool = DDGSearchTool()

        assert hasattr(tool, "name")
        assert hasattr(tool, "description")
        assert hasattr(tool, "inputs")
        assert hasattr(tool, "output_type")
        assert hasattr(tool, "forward")

        assert "query" in tool.inputs
        assert tool.inputs["query"]["type"] == "string"
        assert tool.output_type == "string"

    @patch("mxtoai.tools.web_search.ddg_search.WebSearchTool")
    def test_forward_success(self, mock_web_search_tool):
        """Test successful DDG search execution."""
        mock_ddg_instance = Mock()
        mock_ddg_instance.forward.return_value = "DDG search results"
        mock_web_search_tool.return_value = mock_ddg_instance

        tool = DDGSearchTool(max_results=3)
        result = tool.forward("test query")

        assert result == "DDG search results"
        mock_web_search_tool.assert_called_once_with(engine="duckduckgo", max_results=3)
        mock_ddg_instance.forward.assert_called_once_with(query="test query")

    @patch("mxtoai.tools.web_search.ddg_search.WebSearchTool")
    def test_forward_exception_handling(self, mock_web_search_tool):
        """Test that DDG search exceptions are properly raised."""
        mock_ddg_instance = Mock()
        mock_ddg_instance.forward.side_effect = Exception("DDG search failed")
        mock_web_search_tool.return_value = mock_ddg_instance

        tool = DDGSearchTool()

        with pytest.raises(Exception, match="DDG search failed"):
            tool.forward("test query")

    @patch("mxtoai.tools.web_search.ddg_search.logger")
    @patch("mxtoai.tools.web_search.ddg_search.WebSearchTool")
    def test_logging_behavior(self, mock_web_search_tool, mock_logger):
        """Test that appropriate logging occurs during search."""
        mock_ddg_instance = Mock()
        mock_ddg_instance.forward.return_value = "Results"
        mock_web_search_tool.return_value = mock_ddg_instance

        tool = DDGSearchTool()
        tool.forward("test query")

        mock_logger.info.assert_any_call("Performing DDG search for: test query")
        mock_logger.info.assert_any_call("DDG search completed successfully")


class TestBraveSearchTool:
    """Test the BraveSearchTool functionality."""

    def test_initialization_without_api_key(self):
        """Test BraveSearchTool initialization without API key."""
        with patch.dict(os.environ, {}, clear=True):
            tool = BraveSearchTool()

            assert tool.max_results == 5
            assert tool.api_key is None
            assert tool.name == "brave_search"
            assert "Brave Search API" in tool.description

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    def test_initialization_with_api_key(self):
        """Test BraveSearchTool initialization with API key."""
        tool = BraveSearchTool(max_results=10)

        assert tool.max_results == 10
        assert tool.api_key == "test_api_key"

    def test_forward_without_api_key_raises_error(self):
        """Test that forward raises error when no API key is configured."""
        with patch.dict(os.environ, {}, clear=True):
            tool = BraveSearchTool()

            with pytest.raises(ValueError, match="Brave Search API key not configured"):
                tool.forward("test query")

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    @patch("requests.get")
    def test_forward_success(self, mock_get):
        """Test successful Brave search execution."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Test Result 1",
                        "url": "https://example1.com",
                        "description": "First test result"
                    },
                    {
                        "title": "Test Result 2",
                        "url": "https://example2.com",
                        "description": "Second test result"
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        tool = BraveSearchTool()
        result = tool.forward("test query")

        assert "Test Result 1" in result
        assert "https://example1.com" in result
        assert "First test result" in result
        assert "Test Result 2" in result

        # Verify API call
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert call_args[0][0] == "https://api.search.brave.com/res/v1/web/search"
        assert call_args[1]["headers"]["X-Subscription-Token"] == "test_api_key"
        assert call_args[1]["params"]["q"] == "test query"

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    @patch("requests.get")
    def test_forward_with_custom_parameters(self, mock_get):
        """Test Brave search with custom parameters."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"web": {"results": []}}
        mock_get.return_value = mock_response

        tool = BraveSearchTool()
        tool.forward(
            query="test query",
            country="GB",
            search_lang="fr",
            ui_lang="fr-FR",
            safesearch="strict",
            freshness="pd",
            result_filter="web,news"
        )

        call_params = mock_get.call_args[1]["params"]
        assert call_params["country"] == "GB"
        assert call_params["search_lang"] == "fr"
        assert call_params["ui_lang"] == "fr-FR"
        assert call_params["safesearch"] == "strict"
        assert call_params["freshness"] == "pd"
        assert call_params["result_filter"] == "web,news"

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    @patch("requests.get")
    def test_forward_no_results(self, mock_get):
        """Test Brave search when no results are returned."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"web": {"results": []}}
        mock_get.return_value = mock_response

        tool = BraveSearchTool()
        result = tool.forward("no results query")

        assert "No results found for query: no results query" in result

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    @patch("requests.get")
    def test_forward_http_error(self, mock_get):
        """Test Brave search HTTP error handling."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("API Error")
        mock_get.return_value = mock_response

        tool = BraveSearchTool()

        with pytest.raises(requests.HTTPError):
            tool.forward("test query")

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    @patch("requests.get")
    def test_forward_request_exception(self, mock_get):
        """Test Brave search request exception handling."""
        mock_get.side_effect = requests.RequestException("Network error")

        tool = BraveSearchTool()

        with pytest.raises(requests.RequestException):
            tool.forward("test query")

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_api_key"})
    @patch("mxtoai.tools.web_search.brave_search.logger")
    @patch("requests.get")
    def test_logging_behavior(self, mock_get, mock_logger):
        """Test that appropriate logging occurs during search."""
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "web": {
                "results": [
                    {
                        "title": "Test Result",
                        "url": "https://example.com",
                        "description": "Test description"
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        tool = BraveSearchTool()
        tool.forward("test query")

        # Check that logging occurred - should be at least 1 call
        assert mock_logger.info.call_count >= 1
        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert any("Performing Brave search" in call for call in log_calls)
        assert any("Brave search completed successfully" in call for call in log_calls)


class TestGoogleSearchTool:
    """Test the GoogleSearchTool functionality."""

    def test_initialization_without_api_keys(self):
        """Test GoogleSearchTool initialization without API keys."""
        with patch.dict(os.environ, {}, clear=True):
            tool = GoogleSearchTool()

            assert tool.google_tool is None
            assert tool.name == "google_search"
            assert "Google Search API" in tool.description

    @patch.dict(os.environ, {"SERPAPI_API_KEY": "test_serpapi_key"})
    @patch("mxtoai.tools.web_search.google_search.SmolagentsGoogleSearchTool")
    def test_initialization_with_serpapi(self, mock_google_tool):
        """Test GoogleSearchTool initialization with SerpAPI key."""
        mock_instance = Mock()
        mock_google_tool.return_value = mock_instance

        tool = GoogleSearchTool()

        assert tool.google_tool == mock_instance
        mock_google_tool.assert_called_once_with(provider="serpapi")

    @patch.dict(os.environ, {"SERPER_API_KEY": "test_serper_key"}, clear=True)
    @patch("mxtoai.tools.web_search.google_search.SmolagentsGoogleSearchTool")
    def test_initialization_with_serper(self, mock_google_tool):
        """Test GoogleSearchTool initialization with Serper key."""
        mock_instance = Mock()
        mock_google_tool.return_value = mock_instance

        tool = GoogleSearchTool()

        assert tool.google_tool == mock_instance
        mock_google_tool.assert_called_once_with(provider="serper")

    @patch.dict(os.environ, {"SERPAPI_API_KEY": "test_key", "SERPER_API_KEY": "test_key"})
    @patch("mxtoai.tools.web_search.google_search.SmolagentsGoogleSearchTool")
    def test_initialization_serpapi_priority(self, mock_google_tool):
        """Test that SerpAPI takes priority over Serper when both are available."""
        mock_instance = Mock()
        mock_google_tool.return_value = mock_instance

        GoogleSearchTool()

        # Should use SerpAPI first
        mock_google_tool.assert_called_once_with(provider="serpapi")

    @patch.dict(os.environ, {"SERPAPI_API_KEY": "test_key"})
    @patch("mxtoai.tools.web_search.google_search.SmolagentsGoogleSearchTool")
    def test_initialization_serpapi_failure_fallback(self, mock_google_tool):
        """Test fallback to Serper when SerpAPI initialization fails."""
        # Set both keys to test fallback
        with patch.dict(os.environ, {"SERPER_API_KEY": "test_serper_key"}):
            # Make SerpAPI fail first, then Serper succeed
            side_effects = [ValueError("SerpAPI failed"), Mock()]
            mock_google_tool.side_effect = side_effects

            GoogleSearchTool()

            assert mock_google_tool.call_count == 2
            mock_google_tool.assert_any_call(provider="serpapi")
            mock_google_tool.assert_any_call(provider="serper")

    def test_forward_without_api_configuration_raises_error(self):
        """Test that forward raises error when Google Search API is not configured."""
        with patch.dict(os.environ, {}, clear=True):
            tool = GoogleSearchTool()

            with pytest.raises(ValueError, match="Google Search API not configured"):
                tool.forward("test query")

    @patch.dict(os.environ, {"SERPAPI_API_KEY": "test_key"})
    @patch("mxtoai.tools.web_search.google_search.SmolagentsGoogleSearchTool")
    def test_forward_success(self, mock_google_tool):
        """Test successful Google search execution."""
        mock_instance = Mock()
        mock_instance.forward.return_value = "Google search results"
        mock_google_tool.return_value = mock_instance

        tool = GoogleSearchTool()
        result = tool.forward("test query")

        assert result == "Google search results"
        mock_instance.forward.assert_called_once_with(query="test query")

    @patch.dict(os.environ, {"SERPAPI_API_KEY": "test_key"})
    @patch("mxtoai.tools.web_search.google_search.SmolagentsGoogleSearchTool")
    def test_forward_exception_handling(self, mock_google_tool):
        """Test that Google search exceptions are properly raised."""
        mock_instance = Mock()
        mock_instance.forward.side_effect = Exception("Google search failed")
        mock_google_tool.return_value = mock_instance

        tool = GoogleSearchTool()

        with pytest.raises(Exception, match="Google search failed"):
            tool.forward("test query")

    @patch.dict(os.environ, {"SERPAPI_API_KEY": "test_key"})
    @patch("mxtoai.tools.web_search.google_search.logger")
    @patch("mxtoai.tools.web_search.google_search.SmolagentsGoogleSearchTool")
    def test_logging_behavior(self, mock_google_tool, mock_logger):
        """Test that appropriate logging occurs during search."""
        mock_instance = Mock()
        mock_instance.forward.return_value = "Results"
        mock_google_tool.return_value = mock_instance

        tool = GoogleSearchTool()
        tool.forward("test query")

        mock_logger.info.assert_any_call("Performing Google search for: test query")
        mock_logger.info.assert_any_call("Google search completed successfully")

    @patch.dict(os.environ, {"SERPAPI_API_KEY": "test_key"})
    @patch("mxtoai.tools.web_search.google_search.logger")
    @patch("mxtoai.tools.web_search.google_search.SmolagentsGoogleSearchTool")
    def test_logging_on_error(self, mock_google_tool, mock_logger):
        """Test logging behavior when search fails."""
        mock_instance = Mock()
        mock_instance.forward.side_effect = Exception("Search failed")
        mock_google_tool.return_value = mock_instance

        tool = GoogleSearchTool()

        with pytest.raises(Exception):
            tool.forward("test query")

        mock_logger.error.assert_called_once()
        error_call = mock_logger.error.call_args[0][0]
        assert "Google search failed" in error_call

    def test_tool_interface_compliance(self):
        """Test that GoogleSearchTool complies with Tool interface."""
        tool = GoogleSearchTool()

        assert hasattr(tool, "name")
        assert hasattr(tool, "description")
        assert hasattr(tool, "inputs")
        assert hasattr(tool, "output_type")
        assert hasattr(tool, "forward")

        assert "query" in tool.inputs
        assert tool.inputs["query"]["type"] == "string"
        assert tool.output_type == "string"


class TestIntegrationScenarios:
    """Test realistic integration scenarios for web search tools."""

    def test_fallback_tool_integration(self):
        """Test realistic scenario using tools with FallbackWebSearchTool."""
        from mxtoai.tools.fallback_search_tool import FallbackWebSearchTool

        # Mock DDG as primary
        ddg_tool = Mock()
        ddg_tool.name = "ddg_search"
        ddg_tool.forward.return_value = "DDG results"

        # Mock Brave as secondary
        brave_tool = Mock()
        brave_tool.name = "brave_search"
        brave_tool.forward.return_value = "Brave results"

        fallback_tool = FallbackWebSearchTool(
            primary_tool=ddg_tool,
            secondary_tool=brave_tool
        )

        result = fallback_tool.forward("integration test query")
        assert result == "DDG results"
        ddg_tool.forward.assert_called_once_with(query="integration test query")
        brave_tool.forward.assert_not_called()

    @patch.dict(os.environ, {"BRAVE_SEARCH_API_KEY": "test_key"})
    @patch("requests.get")
    def test_error_resilience(self, mock_get):
        """Test error resilience across different search tools."""
        # Test that each tool handles various error scenarios
        tools = [
            BraveSearchTool(),
        ]

        error_scenarios = [
            requests.HTTPError("HTTP 500"),
            requests.ConnectionError("Connection failed"),
            requests.Timeout("Request timeout"),
            ValueError("Invalid response format")
        ]

        for tool in tools:
            for error in error_scenarios:
                mock_get.side_effect = error

                with pytest.raises(type(error)):
                    tool.forward("error test query")
