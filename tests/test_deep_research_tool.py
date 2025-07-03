import base64
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from mxtoai.tools.deep_research_tool import DeepResearchTool


class TestDeepResearchToolInitialization:
    """Test DeepResearchTool initialization and configuration."""

    @patch.dict(os.environ, {"JINA_API_KEY": "test_api_key"})
    def test_initialization_with_api_key(self):
        """Test successful initialization with API key."""
        tool = DeepResearchTool()

        assert tool.name == "deep_research"
        assert "deep research" in tool.description.lower()
        assert tool.output_type == "object"
        assert tool.api_key == "test_api_key"
        assert tool.api_url == "https://deepsearch.jina.ai/v1/chat/completions"
        assert tool.should_encode_messages is True
        assert tool.use_mock_service is False
        assert tool.deep_research_enabled is False
        assert tool.max_file_size == 10 * 1024 * 1024

    @patch.dict(os.environ, {}, clear=True)
    def test_initialization_without_api_key(self):
        """Test initialization without API key."""
        tool = DeepResearchTool()

        assert tool.api_key is None
        assert "deep research" in tool.description.lower()

    def test_initialization_with_mock_service(self):
        """Test initialization with mock service enabled."""
        tool = DeepResearchTool(use_mock_service=True)

        assert tool.use_mock_service is True
        assert tool.mock_service is not None

    def test_enable_disable_deep_research(self):
        """Test enabling and disabling deep research functionality."""
        tool = DeepResearchTool()

        assert tool.deep_research_enabled is False

        tool.enable_deep_research()
        assert tool.deep_research_enabled is True

        tool.disable_deep_research()
        assert tool.deep_research_enabled is False

    def test_input_schema_validation(self):
        """Test that input schema is properly defined."""
        tool = DeepResearchTool()

        assert "query" in tool.inputs
        assert tool.inputs["query"]["type"] == "string"
        assert "context" in tool.inputs
        assert tool.inputs["context"]["nullable"] is True
        assert "memory_attachments" in tool.inputs
        assert "thread_messages" in tool.inputs
        assert "stream" in tool.inputs
        assert "reasoning_effort" in tool.inputs
        assert tool.inputs["reasoning_effort"]["enum"] == ["low", "medium", "high"]


class TestMemoryContentEncoding:
    """Test memory-based content encoding functionality."""

    def test_encode_content_from_memory_success(self):
        """Test successful content encoding from memory."""
        tool = DeepResearchTool()

        content = b"Test file content"
        result = tool._encode_content_from_memory(content, "test.txt", "text/plain")

        assert result is not None
        assert result["type"] == "file"
        assert result["data"].startswith("data:text/plain;base64,")
        assert result["mimeType"] == "text/plain"

        # Decode and verify content
        encoded_content = result["data"].split(",")[1]
        decoded_content = base64.b64decode(encoded_content)
        assert decoded_content == content

    def test_encode_content_from_memory_large_content(self):
        """Test encoding of content that exceeds size limit."""
        tool = DeepResearchTool()

        # Create content larger than 10MB
        large_content = b"x" * (11 * 1024 * 1024)
        result = tool._encode_content_from_memory(large_content, "large.bin", "application/octet-stream")

        assert result is None

    def test_encode_content_from_memory_mime_type_guessing(self):
        """Test MIME type guessing when not provided."""
        tool = DeepResearchTool()

        content = b"Test content"
        result = tool._encode_content_from_memory(content, "test.txt")

        assert result is not None
        assert result["mimeType"] == "text/plain"

    def test_encode_content_from_memory_binary_content(self):
        """Test encoding of binary content."""
        tool = DeepResearchTool()

        binary_content = b"\x00\x01\x02\x03"
        result = tool._encode_content_from_memory(binary_content, "test.bin", "application/octet-stream")

        assert result is not None
        assert result["type"] == "file"
        assert result["mimeType"] == "application/octet-stream"

        # Decode and verify content
        encoded_content = result["data"].split(",")[1]
        decoded_content = base64.b64decode(encoded_content)
        assert decoded_content == binary_content

    def test_encode_file_deprecated(self):
        """Test that the deprecated _encode_file method returns None."""
        tool = DeepResearchTool()

        result = tool._encode_file("/some/path/file.txt")
        assert result is None


class TestTextEncoding:
    """Test text encoding functionality."""

    def test_encode_text_enabled(self):
        """Test text encoding when enabled."""
        tool = DeepResearchTool()
        tool.should_encode_messages = True

        text = "Hello & world @ test #hashtag"
        result = tool._encode_text(text)

        assert result == "Hello%20%26%20world%20%40%20test%20%23hashtag"

    def test_encode_text_disabled(self):
        """Test text encoding when disabled."""
        tool = DeepResearchTool()
        tool.should_encode_messages = False

        text = "Hello & world @ test #hashtag"
        result = tool._encode_text(text)

        assert result == text

    def test_encode_text_special_characters(self):
        """Test encoding of various special characters."""
        tool = DeepResearchTool()
        tool.should_encode_messages = True

        text = "test@example.com?param=value&other=data"
        result = tool._encode_text(text)

        assert "%" in result  # URL encoded
        assert "@" not in result
        assert "?" not in result
        assert "&" not in result


class TestMessagePreparation:
    """Test message preparation for API calls."""

    def test_prepare_messages_basic_query(self):
        """Test basic message preparation with just query."""
        tool = DeepResearchTool()

        messages = tool._prepare_messages("What is AI?")

        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert len(messages[0]["content"]) == 1
        assert messages[0]["content"][0]["type"] == "text"
        assert "What%20is%20AI" in messages[0]["content"][0]["text"]

    def test_prepare_messages_with_context(self):
        """Test message preparation with context."""
        tool = DeepResearchTool()

        messages = tool._prepare_messages(query="What is AI?", context="This is about machine learning")

        assert len(messages) == 1
        assert len(messages[0]["content"]) == 2
        assert messages[0]["content"][0]["type"] == "text"
        assert messages[0]["content"][1]["type"] == "text"
        assert "What%20is%20AI" in messages[0]["content"][0]["text"]
        assert "machine%20learning" in messages[0]["content"][1]["text"]

    def test_prepare_messages_with_thread_messages(self):
        """Test message preparation with thread messages."""
        tool = DeepResearchTool()

        thread_messages = [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"},
        ]

        messages = tool._prepare_messages(query="Follow-up question", thread_messages=thread_messages)

        assert len(messages) == 1
        assert len(messages[0]["content"]) == 2
        # Check thread messages are included and URL encoded
        thread_content = messages[0]["content"][1]["text"]
        assert "Previous%20Messages" in thread_content
        assert "Previous%20question" in thread_content

    def test_prepare_messages_with_memory_attachments(self):
        """Test message preparation with memory attachments."""
        tool = DeepResearchTool()

        # Test with memory attachments instead of file paths
        memory_attachments = {"test.txt": (b"Test file content", "text/plain")}

        messages = tool._prepare_messages(query="Analyze this file", memory_attachments=memory_attachments)

        assert len(messages) == 1
        assert len(messages[0]["content"]) == 2  # Query + file
        # Check file data is included
        file_content = messages[0]["content"][1]
        assert file_content["type"] == "file"
        assert "data:text/plain;base64," in file_content["data"]

    def test_prepare_messages_attachment_size_limit(self):
        """Test that large attachments are skipped."""
        tool = DeepResearchTool()

        # Create large content (more than 10MB)
        large_content = b"x" * (11 * 1024 * 1024)
        memory_attachments = {"large.bin": (large_content, "application/octet-stream")}

        messages = tool._prepare_messages(query="Analyze this file", memory_attachments=memory_attachments)

        # Large file should be skipped - only query content should remain
        assert len(messages[0]["content"]) == 1


class TestAPIIntegration:
    """Test API integration functionality."""

    @patch.dict(os.environ, {"JINA_API_KEY": "test_api_key"})
    @patch("requests.post")
    def test_forward_success_non_streaming(self, mock_post):
        """Test successful API call without streaming."""
        tool = DeepResearchTool()
        tool.enable_deep_research()

        # Mock successful API response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "AI stands for Artificial Intelligence...",
                        "annotations": [
                            {"title": "Source 1", "url": "http://example1.com"},
                            {"title": "Source 2", "url": "http://example2.com"},
                        ],
                    }
                }
            ],
            "visitedURLs": ["http://example1.com", "http://example2.com"],
            "readURLs": ["http://example1.com"],
            "usage": {"total_tokens": 150},
        }
        mock_response.headers = {"date": "2024-01-15"}
        mock_post.return_value = mock_response

        result = tool.forward(query="What is AI?")

        assert "findings" in result
        assert "annotations" in result
        assert "visited_urls" in result
        assert "read_urls" in result
        assert result["query"] == "What is AI?"
        assert "AI stands for Artificial Intelligence" in result["findings"]

    @patch.dict(os.environ, {"JINA_API_KEY": "test_api_key"})
    @patch("requests.post")
    def test_forward_api_error(self, mock_post):
        """Test API call with HTTP error."""
        tool = DeepResearchTool()
        tool.enable_deep_research()

        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_post.return_value = mock_response

        result = tool.forward(query="What is AI?")

        assert "error" in result
        assert "API request failed with status 500" in str(result["error"])

    @patch.dict(os.environ, {}, clear=True)
    def test_forward_no_api_key(self):
        """Test API call without API key."""
        tool = DeepResearchTool()
        tool.enable_deep_research()

        result = tool.forward(query="What is AI?")

        assert "error" in result
        assert "api key not configured" in str(result["error"]).lower()

    def test_forward_with_mock_service(self):
        """Test using mock service instead of real API."""
        tool = DeepResearchTool(use_mock_service=True)
        tool.enable_deep_research()

        # Mock the mock service
        tool.mock_service.process_request = Mock(
            return_value={
                "choices": [
                    {
                        "message": {
                            "content": "Mock research results",
                            "annotations": [{"title": "Mock source", "url": "http://mock.com"}],
                        }
                    }
                ],
                "visitedURLs": ["http://mock.com"],
                "readURLs": ["http://mock.com"],
                "usage": {"total_tokens": 100},
            }
        )

        result = tool.forward(query="What is AI?")

        assert "findings" in result
        assert "Mock research results" in result["findings"]


class TestContentFormatting:
    """Test content formatting and processing."""

    def test_structure_research_content(self):
        """Test research content structuring."""
        tool = DeepResearchTool()

        content = "This is research content with sources and information."
        structured = tool._structure_research_content(content)

        assert isinstance(structured, str)
        assert len(structured) > 0

    def test_format_research_content_with_sources(self):
        """Test formatting research content with sources."""
        tool = DeepResearchTool()

        content = "Research findings about AI"
        annotations = [
            {"title": "Source 1", "url": "http://example1.com"},
            {"title": "Source 2", "url": "http://example2.com"},
        ]
        visited_urls = ["http://visited1.com"]
        read_urls = ["http://read1.com"]

        formatted = tool._format_research_content(content, annotations, visited_urls, read_urls)

        assert "Research findings about AI" in formatted
        assert "References" in formatted
        assert "http://read1.com" in formatted
        assert "http://visited1.com" in formatted

    def test_format_research_content_no_sources(self):
        """Test formatting research content without sources."""
        tool = DeepResearchTool()

        content = "Research findings about AI"
        formatted = tool._format_research_content(content, [], [], [])

        assert "Research findings about AI" in formatted
        assert isinstance(formatted, str)


class TestStreamingResponse:
    """Test streaming response processing."""

    def test_process_stream_response_mock(self):
        """Test processing streaming response."""
        tool = DeepResearchTool()

        # Create mock streaming response
        mock_response = Mock()
        mock_response.iter_lines.return_value = [
            b'data: {"choices": [{"delta": {"content": "Hello"}}]}',
            b'data: {"choices": [{"delta": {"content": " world"}}]}',
            b"data: [DONE]",
        ]
        mock_response.headers = {"date": "2024-01-15"}

        result = tool._process_stream_response(mock_response)

        # Should have printed streaming content
        assert "findings" in result
        assert "Hello world" in result["findings"]

    def test_process_stream_response_error(self):
        """Test processing streaming response with error."""
        tool = DeepResearchTool()

        # Create mock streaming response with error
        mock_response = Mock()
        mock_response.iter_lines.return_value = [b'data: {"error": {"message": "API Error"}}']

        result = tool._process_stream_response(mock_response)

        assert "error" in result
        assert "API Error" in result["error"]


class TestErrorHandling:
    """Test error handling scenarios."""

    @patch.dict(os.environ, {"JINA_API_KEY": "test_key"})
    def test_forward_json_decode_error(self):
        """Test handling of JSON decode errors."""
        tool = DeepResearchTool()
        tool.enable_deep_research()

        with patch("requests.post") as mock_post:
            mock_response = Mock()
            mock_response.ok = True
            mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
            mock_post.return_value = mock_response

            result = tool.forward(query="Test query")

            assert "error" in result
            assert "JSON" in str(result["error"])

    @patch.dict(os.environ, {"JINA_API_KEY": "test_key"})
    def test_forward_connection_error(self):
        """Test handling of connection errors."""
        tool = DeepResearchTool()
        tool.enable_deep_research()

        with patch("requests.post") as mock_post:
            mock_post.side_effect = requests.ConnectionError("Connection failed")

            result = tool.forward(query="Test query")

            assert "error" in result
            assert "Connection failed" in str(result["error"])

    @patch.dict(os.environ, {"JINA_API_KEY": "test_key"})
    def test_forward_general_exception(self):
        """Test handling of general exceptions."""
        tool = DeepResearchTool()
        tool.enable_deep_research()

        with patch("requests.post") as mock_post:
            mock_post.side_effect = Exception("Unexpected error")

            result = tool.forward(query="Test query")

            assert "error" in result
            assert "Unexpected error" in str(result["error"])

    @patch.dict(os.environ, {"JINA_API_KEY": "test_key"})
    def test_research_disabled_workflow(self):
        """Test workflow when deep research is disabled."""
        tool = DeepResearchTool()
        # Research is disabled by default

        result = tool.forward(query="What is AI?")

        assert "error" in result
        assert "deep research disabled" in str(result["error"]).lower()


class TestIntegrationScenarios:
    """Test integrated workflow scenarios."""

    @patch.dict(os.environ, {"JINA_API_KEY": "test_api_key"})
    @patch("requests.post")
    def test_complete_research_workflow(self, mock_post):
        """Test complete research workflow with all features."""
        tool = DeepResearchTool()
        tool.enable_deep_research()

        # Create test file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("Test document content")
            temp_path = f.name

        try:
            # Mock API response
            mock_response = Mock()
            mock_response.ok = True
            mock_response.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "content": "Comprehensive research results based on the query and attached document.",
                            "annotations": [
                                {"title": "Academic Source", "url": "http://academic.com/paper"},
                                {"title": "News Article", "url": "http://news.com/article"},
                            ],
                        }
                    }
                ],
                "visitedURLs": ["http://site1.com", "http://site2.com"],
                "readURLs": ["http://academic.com/paper"],
                "usage": {"total_tokens": 300},
            }
            mock_response.headers = {"date": "2024-01-15"}
            mock_post.return_value = mock_response

            # Read file content into memory for the new memory_attachments parameter
            with Path(temp_path).open("rb") as f:
                file_content = f.read()

            # Execute complete workflow using memory_attachments
            result = tool.forward(
                query="Analyze the uploaded document and provide insights",
                context="This is a research project about AI development",
                memory_attachments={"research_notes.txt": (file_content, "text/plain")},
                thread_messages=[
                    {"role": "user", "content": "Previous question about AI"},
                    {"role": "assistant", "content": "Previous answer about AI"},
                ],
                reasoning_effort="high",
            )

            # Verify results
            assert "findings" in result
            assert "annotations" in result
            assert "visited_urls" in result
            assert "read_urls" in result
            assert result["query"] == "Analyze the uploaded document and provide insights"
            assert "Comprehensive research results" in result["findings"]

        finally:
            Path(temp_path).unlink()

    @patch.dict(os.environ, {"JINA_API_KEY": "test_api_key"})
    @patch("requests.post")
    def test_streaming_workflow(self, mock_post):
        """Test streaming research workflow."""
        tool = DeepResearchTool()
        tool.enable_deep_research()

        # Mock streaming response
        mock_response = Mock()
        mock_response.ok = True
        mock_response.iter_lines.return_value = [
            b'data: {"choices": [{"delta": {"content": "Streaming"}}]}',
            b'data: {"choices": [{"delta": {"content": " research"}}]}',
            b'data: {"choices": [{"delta": {"content": " results"}}]}',
            b"data: [DONE]",
        ]
        mock_response.headers = {"date": "2024-01-15"}
        mock_post.return_value = mock_response

        result = tool.forward(query="What is machine learning?", stream=True)

        # Verify streaming results
        assert "findings" in result
        assert "Streaming research results" in result["findings"]
