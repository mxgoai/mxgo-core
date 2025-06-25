from unittest.mock import Mock, patch

import pytest

from mxtoai.tools.fallback_search_tool import FallbackWebSearchTool


class TestFallbackWebSearchTool:
    """Test the FallbackWebSearchTool functionality."""

    def test_initialization_with_both_tools(self):
        """Test successful initialization with both primary and secondary tools."""
        primary_tool = Mock()
        secondary_tool = Mock()

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)

        assert tool.primary_tool == primary_tool
        assert tool.secondary_tool == secondary_tool
        assert tool.name == "web_search"
        assert "Performs a web search" in tool.description

    def test_initialization_with_primary_only(self):
        """Test initialization with only primary tool."""
        primary_tool = Mock()

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=None)

        assert tool.primary_tool == primary_tool
        assert tool.secondary_tool is None

    def test_initialization_with_secondary_only(self):
        """Test initialization with only secondary tool."""
        secondary_tool = Mock()

        tool = FallbackWebSearchTool(primary_tool=None, secondary_tool=secondary_tool)

        assert tool.primary_tool is None
        assert tool.secondary_tool == secondary_tool

    def test_initialization_with_no_tools_raises_error(self):
        """Test that initialization with no tools raises ValueError."""
        with pytest.raises(ValueError, match="FallbackWebSearchTool requires at least one search tool"):
            FallbackWebSearchTool(primary_tool=None, secondary_tool=None)

    def test_forward_primary_success(self):
        """Test successful search with primary tool."""
        primary_tool = Mock()
        secondary_tool = Mock()

        primary_tool.name = "google_search"
        primary_tool.forward.return_value = "Primary search results"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)
        result = tool.forward("test query")

        assert result == "Primary search results"
        primary_tool.forward.assert_called_once_with(query="test query")
        secondary_tool.forward.assert_not_called()

    def test_forward_primary_fails_secondary_succeeds(self):
        """Test fallback to secondary tool when primary fails."""
        primary_tool = Mock()
        secondary_tool = Mock()

        primary_tool.name = "google_search"
        secondary_tool.name = "ddg_search"

        primary_tool.forward.side_effect = Exception("Primary tool failed")
        secondary_tool.forward.return_value = "Secondary search results"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)
        result = tool.forward("test query")

        assert result == "Secondary search results"
        primary_tool.forward.assert_called_once_with(query="test query")
        secondary_tool.forward.assert_called_once_with(query="test query")

    def test_forward_both_tools_fail(self):
        """Test exception when both tools fail."""
        primary_tool = Mock()
        secondary_tool = Mock()

        primary_tool.name = "google_search"
        secondary_tool.name = "ddg_search"

        primary_tool.forward.side_effect = Exception("Primary failed")
        secondary_tool.forward.side_effect = Exception("Secondary failed")

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)

        with pytest.raises(Exception, match="Both primary and secondary search tools failed"):
            tool.forward("test query")

    def test_forward_primary_only_success(self):
        """Test successful search with only primary tool configured."""
        primary_tool = Mock()
        primary_tool.name = "google_search"
        primary_tool.forward.return_value = "Primary results"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=None)
        result = tool.forward("test query")

        assert result == "Primary results"
        primary_tool.forward.assert_called_once_with(query="test query")

    def test_forward_primary_only_fails(self):
        """Test exception when only primary tool configured and it fails."""
        primary_tool = Mock()
        primary_tool.name = "google_search"
        primary_tool.forward.side_effect = Exception("Primary failed")

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=None)

        with pytest.raises(Exception, match="Primary search tool failed and no fallback tool is configured"):
            tool.forward("test query")

    def test_forward_secondary_only_success(self):
        """Test successful search with only secondary tool configured."""
        secondary_tool = Mock()
        secondary_tool.name = "ddg_search"
        secondary_tool.forward.return_value = "Secondary results"

        tool = FallbackWebSearchTool(primary_tool=None, secondary_tool=secondary_tool)
        result = tool.forward("test query")

        assert result == "Secondary results"
        secondary_tool.forward.assert_called_once_with(query="test query")

    def test_forward_secondary_only_fails(self):
        """Test exception when only secondary tool configured and it fails."""
        secondary_tool = Mock()
        secondary_tool.name = "ddg_search"
        secondary_tool.forward.side_effect = Exception("Secondary failed")

        tool = FallbackWebSearchTool(primary_tool=None, secondary_tool=secondary_tool)

        with pytest.raises(Exception, match="Both primary and secondary search tools failed"):
            tool.forward("test query")

    def test_logging_on_primary_success(self):
        """Test that appropriate logging occurs on primary success."""
        primary_tool = Mock()
        secondary_tool = Mock()

        primary_tool.name = "google_search"
        primary_tool.forward.return_value = "Results"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)

        with patch("mxtoai.tools.fallback_search_tool.logger") as mock_logger:
            tool.forward("test query")

            mock_logger.debug.assert_any_call("Attempting search with primary tool: google_search")
            mock_logger.debug.assert_any_call("Primary search tool succeeded.")

    def test_logging_on_fallback(self):
        """Test that appropriate logging occurs when falling back to secondary."""
        primary_tool = Mock()
        secondary_tool = Mock()

        primary_tool.name = "google_search"
        secondary_tool.name = "ddg_search"

        primary_tool.forward.side_effect = Exception("Primary failed")
        secondary_tool.forward.return_value = "Secondary results"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)

        with patch("mxtoai.tools.fallback_search_tool.logger") as mock_logger:
            tool.forward("test query")

            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args[0][0]
            assert "Primary search tool (google_search) failed" in warning_call
            assert "Attempting fallback" in warning_call

            mock_logger.debug.assert_any_call("Attempting search with secondary tool: ddg_search")
            mock_logger.debug.assert_any_call("Secondary search tool succeeded.")

    def test_logging_on_both_fail(self):
        """Test logging when both tools fail."""
        primary_tool = Mock()
        secondary_tool = Mock()

        primary_tool.name = "google_search"
        secondary_tool.name = "ddg_search"

        primary_tool.forward.side_effect = Exception("Primary failed")
        secondary_tool.forward.side_effect = Exception("Secondary failed")

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=secondary_tool)

        with patch("mxtoai.tools.fallback_search_tool.logger") as mock_logger:
            with pytest.raises(Exception, match="Both primary and secondary search tools failed"):
                tool.forward("test query")

            mock_logger.error.assert_called_once()
            error_call = mock_logger.error.call_args[0][0]
            assert "Secondary search tool (ddg_search) also failed" in error_call

    def test_tool_interface_compliance(self):
        """Test that the tool complies with smolagents Tool interface."""
        primary_tool = Mock()
        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=None)

        # Check required Tool attributes
        assert hasattr(tool, "name")
        assert hasattr(tool, "description")
        assert hasattr(tool, "inputs")
        assert hasattr(tool, "output_type")
        assert hasattr(tool, "forward")

        # Check input specification
        assert "query" in tool.inputs
        assert tool.inputs["query"]["type"] == "string"
        assert tool.output_type == "string"

    def test_different_query_types(self):
        """Test forward method with different query types and content."""
        primary_tool = Mock()
        primary_tool.name = "test_tool"
        primary_tool.forward.return_value = "Search results"

        tool = FallbackWebSearchTool(primary_tool=primary_tool, secondary_tool=None)

        # Test different query types
        queries = [
            "simple query",
            "complex query with special characters !@#$%",
            "query with numbers 12345",
            "very long query " * 20,
            "query with unicode characters 测试 🔍",
        ]

        for query in queries:
            result = tool.forward(query)
            assert result == "Search results"
            primary_tool.forward.assert_called_with(query=query)
