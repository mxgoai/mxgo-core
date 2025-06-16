from unittest.mock import Mock, patch

import pytest
from smolagents import Tool

from mxtoai.tools.fallback_search_tool import FallbackWebSearchTool


class TestFallbackWebSearchTool:
    """Test the FallbackWebSearchTool functionality."""

    def test_initialization_with_both_tools(self):
        """Test successful initialization with both primary and secondary tools."""
        primary_tool = Mock(spec=Tool)
        primary_tool.name = "google_search"
        secondary_tool = Mock(spec=Tool)
        secondary_tool.name = "duckduckgo_search"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)

        assert tool.primary_tool == primary_tool
        assert tool.secondary_tool == secondary_tool
        assert tool.name == "web_search"
        assert "Performs a web search" in tool.description
        assert "query" in tool.inputs
        assert tool.output_type == "string"

    def test_initialization_with_primary_only(self):
        """Test initialization with only primary tool."""
        primary_tool = Mock(spec=Tool)
        primary_tool.name = "google_search"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=None)

        assert tool.primary_tool == primary_tool
        assert tool.secondary_tool is None

    def test_initialization_with_secondary_only(self):
        """Test initialization with only secondary tool."""
        secondary_tool = Mock(spec=Tool)
        secondary_tool.name = "duckduckgo_search"

        tool = FallbackWebSearchTool(primary_tool=None, secondary_tool=secondary_tool)

        assert tool.primary_tool is None
        assert tool.secondary_tool == secondary_tool

    def test_initialization_with_no_tools_raises_error(self):
        """Test that initialization with no tools raises ValueError."""
        with pytest.raises(ValueError, match="FallbackWebSearchTool requires at least one search tool"):
            FallbackWebSearchTool(primary_tool=None, secondary_tool=None)

    def test_forward_primary_tool_success(self):
        """Test successful search with primary tool."""
        primary_tool = Mock(spec=Tool)
        primary_tool.name = "google_search"
        primary_tool.forward.return_value = "Primary search results"

        secondary_tool = Mock(spec=Tool)
        secondary_tool.name = "duckduckgo_search"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)

        result = tool.forward("test query")

        assert result == "Primary search results"
        primary_tool.forward.assert_called_once_with(query="test query")
        secondary_tool.forward.assert_not_called()

    def test_forward_primary_fails_secondary_succeeds(self):
        """Test fallback to secondary tool when primary fails."""
        primary_tool = Mock(spec=Tool)
        primary_tool.name = "google_search"
        primary_tool.forward.side_effect = Exception("Primary tool failed")

        secondary_tool = Mock(spec=Tool)
        secondary_tool.name = "duckduckgo_search"
        secondary_tool.forward.return_value = "Secondary search results"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)

        with patch("mxtoai.tools.fallback_search_tool.logger") as mock_logger:
            result = tool.forward("test query")

        assert result == "Secondary search results"
        primary_tool.forward.assert_called_once_with(query="test query")
        secondary_tool.forward.assert_called_once_with(query="test query")

        # Check that warning was logged
        mock_logger.warning.assert_called_once()
        assert "Primary search tool" in mock_logger.warning.call_args[0][0]
        assert "failed" in mock_logger.warning.call_args[0][0]

    def test_forward_both_tools_fail(self):
        """Test exception when both tools fail."""
        primary_tool = Mock(spec=Tool)
        primary_tool.name = "google_search"
        primary_tool.forward.side_effect = Exception("Primary failed")

        secondary_tool = Mock(spec=Tool)
        secondary_tool.name = "duckduckgo_search"
        secondary_tool.forward.side_effect = Exception("Secondary failed")

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)

        with pytest.raises(Exception, match="Both primary and secondary search tools failed"):
            tool.forward("test query")

        primary_tool.forward.assert_called_once_with(query="test query")
        secondary_tool.forward.assert_called_once_with(query="test query")

    def test_forward_primary_only_success(self):
        """Test successful search with only primary tool."""
        primary_tool = Mock(spec=Tool)
        primary_tool.name = "google_search"
        primary_tool.forward.return_value = "Primary search results"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=None)

        result = tool.forward("test query")

        assert result == "Primary search results"
        primary_tool.forward.assert_called_once_with(query="test query")

    def test_forward_primary_only_fails(self):
        """Test exception when only primary tool fails and no secondary available."""
        primary_tool = Mock(spec=Tool)
        primary_tool.name = "google_search"
        primary_tool.forward.side_effect = Exception("Primary failed")

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=None)

        with pytest.raises(Exception, match="Primary search tool failed and no fallback tool is configured"):
            tool.forward("test query")

        primary_tool.forward.assert_called_once_with(query="test query")

    def test_forward_secondary_only_success(self):
        """Test successful search with only secondary tool."""
        secondary_tool = Mock(spec=Tool)
        secondary_tool.name = "duckduckgo_search"
        secondary_tool.forward.return_value = "Secondary search results"

        tool = FallbackWebSearchTool(primary_tool=None, secondary_tool=secondary_tool)

        result = tool.forward("test query")

        assert result == "Secondary search results"
        secondary_tool.forward.assert_called_once_with(query="test query")

    def test_forward_secondary_only_fails(self):
        """Test exception when only secondary tool fails."""
        secondary_tool = Mock(spec=Tool)
        secondary_tool.name = "duckduckgo_search"
        secondary_tool.forward.side_effect = Exception("Secondary failed")

        tool = FallbackWebSearchTool(primary_tool=None, secondary_tool=secondary_tool)

        with pytest.raises(Exception, match="Both primary and secondary search tools failed"):
            tool.forward("test query")

        secondary_tool.forward.assert_called_once_with(query="test query")

    def test_logging_behavior(self):
        """Test that appropriate logging occurs during execution."""
        primary_tool = Mock(spec=Tool)
        primary_tool.name = "google_search"
        primary_tool.forward.side_effect = Exception("Connection error")

        secondary_tool = Mock(spec=Tool)
        secondary_tool.name = "duckduckgo_search"
        secondary_tool.forward.return_value = "Fallback results"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)

        with patch("mxtoai.tools.fallback_search_tool.logger") as mock_logger:
            result = tool.forward("test query")

        assert result == "Fallback results"

        # Check debug logs for attempting searches
        debug_calls = [call[0][0] for call in mock_logger.debug.call_args_list]
        assert any("Attempting search with primary tool" in call for call in debug_calls)
        assert any("Attempting search with secondary tool" in call for call in debug_calls)
        assert any("Secondary search tool succeeded" in call for call in debug_calls)

        # Check warning log for primary failure
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "Primary search tool (google_search) failed" in warning_msg
        assert "Attempting fallback" in warning_msg

    def test_tool_name_access_in_logs(self):
        """Test that tool names are properly accessed for logging."""
        primary_tool = Mock(spec=Tool)
        primary_tool.name = "custom_primary"
        primary_tool.forward.side_effect = ValueError("API key missing")

        secondary_tool = Mock(spec=Tool)
        secondary_tool.name = "custom_secondary"
        secondary_tool.forward.side_effect = RuntimeError("Network timeout")

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)

        with patch("mxtoai.tools.fallback_search_tool.logger") as mock_logger, pytest.raises(Exception):
            tool.forward("search query")

        # Verify tool names appear in logs
        warning_call = mock_logger.warning.call_args[0][0]
        assert "custom_primary" in warning_call

        error_call = mock_logger.error.call_args[0][0]
        assert "custom_secondary" in error_call

    def test_empty_query_handling(self):
        """Test handling of empty query strings."""
        primary_tool = Mock(spec=Tool)
        primary_tool.name = "google_search"
        primary_tool.forward.return_value = "Empty query results"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=None)

        result = tool.forward("")

        assert result == "Empty query results"
        primary_tool.forward.assert_called_once_with(query="")

    def test_special_characters_in_query(self):
        """Test handling of queries with special characters."""
        primary_tool = Mock(spec=Tool)
        primary_tool.name = "google_search"
        primary_tool.forward.return_value = "Special char results"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=None)

        special_query = "test & query with @special #characters"
        result = tool.forward(special_query)

        assert result == "Special char results"
        primary_tool.forward.assert_called_once_with(query=special_query)
