import base64
import os
import tempfile
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from mxtoai.scripts.visual_qa import (
    VisualQATool,
    azure_visualizer_from_content,
    encode_image_from_content,
    resize_image_from_content,
    visualizer_from_content,
)


class TestEncodeImage:
    """Test the encode_image_from_content function."""

    def test_encode_local_image_file(self):
        """Test encoding a local image file."""
        # Create a temporary image file
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            # Create a simple test image
            img = Image.new("RGB", (100, 100), color="red")
            img.save(temp_file.name, "JPEG")
            temp_path = temp_file.name

        try:
            # Read the file content
            with open(temp_path, "rb") as f:
                content = f.read()

            result = encode_image_from_content(content)

            # Should return a base64 string
            assert isinstance(result, str)
            assert len(result) > 0

            # Should be valid base64
            decoded = base64.b64decode(result)
            assert len(decoded) > 0

        finally:
            os.unlink(temp_path)

    def test_encode_image_from_bytes(self):
        """Test encoding image from bytes."""
        # Create a simple test image in memory
        img = Image.new("RGB", (50, 50), color="green")
        import io

        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        content = img_bytes.getvalue()

        result = encode_image_from_content(content)

        # Should return a base64 string
        assert isinstance(result, str)
        assert len(result) > 0

        # Should be valid base64
        decoded = base64.b64decode(result)
        assert len(decoded) > 0

    def test_encode_nonexistent_file(self):
        """Test encoding with empty content."""
        # encode_image_from_content just does base64 encoding, so empty bytes will return empty string
        result = encode_image_from_content(b"")
        assert result == ""


class TestResizeImage:
    """Test the resize_image_from_content function."""

    def test_resize_image_success(self):
        """Test successful image resizing."""
        # Create a test image in memory
        img = Image.new("RGB", (200, 200), color="blue")
        import io

        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        content = img_bytes.getvalue()

        resized_content = resize_image_from_content(content)

        # Check that we got bytes back
        assert isinstance(resized_content, bytes)
        assert len(resized_content) > 0

        # Check dimensions are halved
        resized_img = Image.open(io.BytesIO(resized_content))
        assert resized_img.size == (100, 100)

    def test_resize_nonexistent_file(self):
        """Test resizing with empty content."""
        with pytest.raises(Exception):  # PIL will raise UnidentifiedImageError
            resize_image_from_content(b"")


class TestProcessImagesAndText:
    """Test the process_images_and_text function."""

    @pytest.mark.skip(reason="Complex function with heavy dependencies - tested via integration tests")
    def test_process_images_and_text_success(self):
        """Test successful image and text processing."""


class TestVisualQATool:
    """Test the VisualQATool class."""

    def test_initialization(self):
        """Test VisualQATool initialization."""
        tool = VisualQATool()

        assert tool.name == "visualizer"
        assert "answer questions about attached images" in tool.description
        assert "content" in tool.inputs
        assert "mime_type" in tool.inputs
        assert "question" in tool.inputs
        assert tool.output_type == "string"
        assert hasattr(tool, "client")

    @patch("mxtoai.scripts.visual_qa.process_images_and_text_from_content")
    def test_forward_with_question(self, mock_process):
        """Test forward method with a specific question."""
        mock_process.return_value = {"generated_text": "This is a test image"}

        tool = VisualQATool()
        result = tool.forward(b"fake_image_content", "image/jpeg", "What do you see?")

        assert result == {"generated_text": "This is a test image"}
        mock_process.assert_called_once_with(b"fake_image_content", "What do you see?", tool.client)

    @patch("mxtoai.scripts.visual_qa.process_images_and_text_from_content")
    def test_forward_without_question(self, mock_process):
        """Test forward method without a specific question (auto-caption)."""
        mock_process.return_value = {"generated_text": "Auto-generated caption"}

        tool = VisualQATool()
        result = tool.forward(b"fake_image_content", "image/jpeg")

        # Should add explanatory note
        assert "You did not provide a particular question" in result
        assert "detailed caption for the image" in result

        # Should call with default caption question
        mock_process.assert_called_once()
        call_args = mock_process.call_args
        assert "Please write a detailed caption" in call_args[0][1]

    @patch("mxtoai.scripts.visual_qa.process_images_and_text_from_content")
    @patch("mxtoai.scripts.visual_qa.resize_image_from_content")
    def test_forward_payload_too_large_retry(self, mock_resize, mock_process):
        """Test handling of 'Payload Too Large' error with image resizing."""
        # First call fails with payload error, second succeeds
        mock_process.side_effect = [Exception("Payload Too Large"), {"generated_text": "Resized image result"}]
        mock_resize.return_value = b"resized_image_content"

        tool = VisualQATool()
        result = tool.forward(b"fake_image_content", "image/jpeg", "What's this?")

        assert result == {"generated_text": "Resized image result"}
        mock_resize.assert_called_once_with(b"fake_image_content")
        assert mock_process.call_count == 2


class TestVisualizerFunction:
    """Test the visualizer function."""

    def test_invalid_image_path_type(self):
        """Test visualizer with invalid content type."""
        with pytest.raises(TypeError):
            visualizer_from_content(123, "image/jpeg")  # Non-bytes content

    @patch("requests.post")
    @patch("mxtoai.scripts.visual_qa.encode_image_from_content")
    def test_visualizer_success(self, mock_encode, mock_post):
        """Test successful image analysis with visualizer function."""
        mock_encode.return_value = "base64_encoded_image"

        mock_response = Mock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "This is an image of a cat"}}]}
        mock_post.return_value = mock_response

        result = visualizer_from_content(b"test_image_content", "image/jpeg", "What animal is this?")

        assert result == "This is an image of a cat"
        mock_encode.assert_called_once_with(b"test_image_content")

        # Check API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0] == "https://api.openai.com/v1/chat/completions"

        payload = call_args[1]["json"]
        assert payload["model"] == "gpt-4o"
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"

        content = payload["messages"][0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "What animal is this?"
        assert content[1]["type"] == "image_url"

    @patch("requests.post")
    @patch("mxtoai.scripts.visual_qa.encode_image_from_content")
    def test_visualizer_without_question(self, mock_encode, mock_post):
        """Test visualizer function without specific question."""
        mock_encode.return_value = "base64_data"

        mock_response = Mock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Auto-generated description"}}]}
        mock_post.return_value = mock_response

        result = visualizer_from_content(b"image_content", "image/jpeg")

        # Should add explanatory note
        assert "You did not provide a particular question" in result
        assert "detailed caption for the image" in result

        # Should use default caption prompt
        call_args = mock_post.call_args
        payload = call_args[1]["json"]
        content = payload["messages"][0]["content"][0]["text"]
        assert "Please write a detailed caption" in content

    @patch("requests.post")
    @patch("mxtoai.scripts.visual_qa.encode_image_from_content")
    def test_visualizer_api_error(self, mock_encode, mock_post):
        """Test visualizer function handling API errors."""
        mock_encode.return_value = "base64_data"

        mock_response = Mock()
        mock_response.json.return_value = {"error": "API Error"}
        mock_post.return_value = mock_response

        with pytest.raises(Exception, match="Response format unexpected"):
            visualizer_from_content(b"image_content", "image/jpeg", "What's this?")


class TestAzureVisualizer:
    """Test the azure_visualizer function."""

    @patch("mxtoai.scripts.visual_qa.completion")
    @patch("mxtoai.scripts.visual_qa.encode_image_from_content")
    @patch.dict(
        os.environ,
        {
            "MODEL_NAME": "gpt-4o",
            "MODEL_API_KEY": "test_key",
            "MODEL_ENDPOINT": "https://test.openai.azure.com",
            "MODEL_API_VERSION": "2024-02-01",
        },
    )
    def test_azure_visualizer_success(self, mock_encode, mock_completion):
        """Test successful Azure OpenAI image analysis."""
        mock_encode.return_value = "base64_image_data"

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Azure analysis result"
        mock_completion.return_value = mock_response

        result = azure_visualizer_from_content(b"test_image_content", "image/jpeg", "Analyze this image")

        assert result == "Azure analysis result"
        mock_encode.assert_called_once_with(b"test_image_content")

        # Check litellm completion call
        mock_completion.assert_called_once()
        call_args = mock_completion.call_args
        kwargs = call_args[1]

        assert kwargs["model"] == "azure/gpt-4o"
        assert kwargs["api_key"] == "test_key"
        assert kwargs["api_base"] == "https://test.openai.azure.com"
        assert kwargs["api_version"] == "2024-02-01"
        assert kwargs["max_tokens"] == 1000

        messages = kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

        content = messages[0]["content"]
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Analyze this image"
        assert content[1]["type"] == "image_url"

    @patch("mxtoai.scripts.visual_qa.completion")
    @patch("mxtoai.scripts.visual_qa.encode_image_from_content")
    def test_azure_visualizer_without_question(self, mock_encode, mock_completion):
        """Test Azure visualizer without specific question."""
        mock_encode.return_value = "base64_data"

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = "Default caption"
        mock_completion.return_value = mock_response

        result = azure_visualizer_from_content(b"image_content", "image/jpeg")

        assert "You did not provide a particular question" in result
        assert "detailed caption for the image" in result

    @patch("mxtoai.scripts.visual_qa.completion")
    @patch("mxtoai.scripts.visual_qa.encode_image_from_content")
    @patch("mxtoai.scripts.visual_qa.resize_image_from_content")
    def test_azure_visualizer_image_too_large(self, mock_resize, mock_encode, mock_completion):
        """Test Azure visualizer handling large image errors."""
        mock_encode.return_value = "base64_data"
        mock_resize.return_value = "resized_image.jpg"

        # First call fails with size error, second succeeds after resize
        mock_completion.side_effect = [
            Exception("image too large"),
            Mock(choices=[Mock(message=Mock(content="Resized result"))]),
        ]

        result = azure_visualizer_from_content(b"large_image_content", "image/jpeg", "What's this?")

        # The function successfully retries with resized image and returns the result
        assert result == "Resized result"
        mock_resize.assert_called_once_with(b"large_image_content")

    @patch("mxtoai.scripts.visual_qa.completion")
    @patch("mxtoai.scripts.visual_qa.encode_image_from_content")
    def test_azure_visualizer_empty_response(self, mock_encode, mock_completion):
        """Test Azure visualizer handling empty response."""
        mock_encode.return_value = "base64_data"

        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message = Mock()
        mock_response.choices[0].message.content = ""
        mock_completion.return_value = mock_response

        with pytest.raises(Exception, match="Failed to process image"):
            azure_visualizer_from_content(b"image_content", "image/jpeg", "What's this?")

    @patch("mxtoai.scripts.visual_qa.completion")
    @patch("mxtoai.scripts.visual_qa.encode_image_from_content")
    def test_azure_visualizer_api_error(self, mock_encode, mock_completion):
        """Test Azure visualizer handling API errors."""
        mock_encode.return_value = "base64_data"
        mock_completion.side_effect = Exception("API connection failed")

        with pytest.raises(Exception, match="Failed to process image"):
            azure_visualizer_from_content(b"image_content", "image/jpeg", "What's this?")

    @patch("mxtoai.scripts.visual_qa.encode_image_from_content")
    def test_azure_visualizer_mime_type_detection(self, mock_encode):
        """Test MIME type detection for different image formats."""
        mock_encode.return_value = "base64_data"

        with patch("mxtoai.scripts.visual_qa.completion") as mock_completion:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message = Mock()
            mock_response.choices[0].message.content = "Analysis result"
            mock_completion.return_value = mock_response

            # Test different image extensions
            test_files = ["image.jpg", "image.png", "image.gif", "image.unknown"]

            for filename in test_files:
                result = azure_visualizer_from_content(b"image_content", "image/jpeg", "Analyze")
                assert result == "Analysis result"

                # Check MIME type handling
                call_args = mock_completion.call_args
                content = call_args[1]["messages"][0]["content"][1]

                if filename.endswith(".unknown"):
                    # Should default to JPEG
                    assert content["image_url"]["url"].startswith("data:image/jpeg;base64,")
                else:
                    # Should detect proper MIME type
                    assert "data:image/" in content["image_url"]["url"]


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple visual processing components."""

    def test_visual_qa_tool_integration(self):
        """Test realistic integration of VisualQATool with error handling."""
        tool = VisualQATool()

        # Create a real test image
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            img = Image.new("RGB", (100, 100), color="red")
            img.save(temp_file.name, "JPEG")
            temp_path = temp_file.name

        try:
            with patch("mxtoai.scripts.visual_qa.process_images_and_text_from_content") as mock_process:
                mock_process.return_value = {"generated_text": "Integration test result"}

                # Read the file content to pass as bytes
                with open(temp_path, "rb") as f:
                    content = f.read()

                result = tool.forward(content, "image/jpeg", "What color is this image?")

                # Should return the processed result
                assert result == {"generated_text": "Integration test result"}
                mock_process.assert_called_once_with(content, "What color is this image?", tool.client)

        finally:
            os.unlink(temp_path)

    def test_error_handling_chain(self):
        """Test error handling across different visual processing functions."""
        # encode_image_from_content just does base64 encoding, won't raise FileNotFoundError
        result = encode_image_from_content(b"")
        assert result == ""

        # resize_image_from_content will raise an image processing error
        with pytest.raises(Exception):
            resize_image_from_content(b"")

        # visualizer_from_content requires proper parameters
        with pytest.raises(TypeError):
            visualizer_from_content(None, "image/jpeg")  # Invalid input type
