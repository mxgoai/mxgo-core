import base64
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from PIL import Image

from mxgo.scripts.visual_qa import (
    AzureVisualizerTool,
    HuggingFaceVisualizerTool,
    OpenAIVisualizerTool,
    azure_visualizer,
    encode_image,
    resize_image,
    visualizer,
)


class TestEncodeImage:
    """Test the encode_image function."""

    def test_encode_local_image_file(self):
        """Test encoding a local image file."""
        # Create a temporary test image
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            img = Image.new("RGB", (10, 10), color="red")
            img.save(temp_file.name, "JPEG")
            temp_path = temp_file.name

        try:
            # Test the function
            result = encode_image(temp_path)

            # Should return base64 string
            assert isinstance(result, str)
            assert len(result) > 0

            # Should be valid base64 (rough check)
            try:
                base64.b64decode(result)
                assert True
            except Exception:
                pytest.fail("Result is not valid base64")
        finally:
            # Clean up
            Path(temp_path).unlink()

    @patch("requests.get")
    def test_encode_remote_image_url(self, mock_get):
        """Test encoding a remote image URL."""
        # Mock the response
        mock_response = Mock()
        mock_response.content = b"fake_image_data"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = encode_image("https://example.com/image.jpg")

        # Should return base64 string
        assert isinstance(result, str)
        assert len(result) > 0

        # Should have called requests.get
        mock_get.assert_called_once_with("https://example.com/image.jpg", timeout=30)

    @patch("requests.get")
    def test_encode_remote_image_no_extension(self, mock_get):
        """Test encoding a remote image URL without extension."""
        # Mock the response
        mock_response = Mock()
        mock_response.content = b"fake_image_data"
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        result = encode_image("https://example.com/image")

        # Should return base64 string
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_nonexistent_file(self):
        """Test encoding a file that doesn't exist."""
        with pytest.raises(FileNotFoundError):
            encode_image("nonexistent_file.jpg")


class TestResizeImage:
    """Test the resize_image function."""

    def test_resize_image_success(self):
        """Test successful image resizing."""
        # Create a temporary test image
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            img = Image.new("RGB", (2048, 1536), color="blue")  # Large image
            img.save(temp_file.name, "JPEG")
            temp_path = temp_file.name

        try:
            # Test the function
            resized_path = resize_image(temp_path, max_dimension=1024)

            # Should return a different path
            assert resized_path != temp_path
            assert Path(resized_path).exists()

            # Check that image was actually resized
            resized_img = Image.open(resized_path)
            width, height = resized_img.size
            assert max(width, height) <= 1024

            # Clean up resized image
            Path(resized_path).unlink()
        finally:
            # Clean up original
            Path(temp_path).unlink()


class TestProcessImagesAndText:
    """Test the process_images_and_text function."""

    @pytest.mark.skip(reason="Complex function with heavy dependencies - tested via integration tests")
    def test_process_images_and_text_success(self):
        """Test successful image processing with text."""


class TestHuggingFaceVisualizerTool:
    """Test the HuggingFaceVisualizerTool class."""

    def test_initialization(self):
        """Test HuggingFaceVisualizerTool initialization."""
        tool = HuggingFaceVisualizerTool()

        assert tool.name == "huggingface_visualizer"
        assert "answer questions about attached images" in tool.description
        assert "image_path" in tool.inputs
        assert "question" in tool.inputs
        assert tool.output_type == "string"
        assert hasattr(tool, "client")

    @patch("mxgo.scripts.visual_qa.process_images_and_text")
    def test_forward_with_question(self, mock_process):
        """Test forward method with a specific question."""
        mock_process.return_value = "This is a test image"

        tool = HuggingFaceVisualizerTool()
        result = tool.forward("test_image.jpg", "What do you see?")

        assert result == "This is a test image"
        mock_process.assert_called_once_with("test_image.jpg", "What do you see?", tool.client)

    @patch("mxgo.scripts.visual_qa.process_images_and_text")
    def test_forward_without_question(self, mock_process):
        """Test forward method without a specific question (auto-caption)."""
        mock_process.return_value = "Auto-generated caption"

        tool = HuggingFaceVisualizerTool()
        result = tool.forward("test_image.jpg")

        # Should add explanatory note
        assert "You did not provide a particular question" in result
        assert "detailed caption for the image" in result

        # Should call with default caption question
        mock_process.assert_called_once()
        call_args = mock_process.call_args
        assert "Please write a detailed caption" in call_args[0][1]

    @patch("mxgo.scripts.visual_qa.process_images_and_text")
    @patch("mxgo.scripts.visual_qa.resize_image")
    def test_forward_payload_too_large_retry(self, mock_resize, mock_process):
        """Test forward method with payload too large error and retry."""
        mock_resize.return_value = "resized_image.jpg"

        # First call fails with "Payload Too Large", second succeeds
        mock_process.side_effect = [Exception("Payload Too Large"), "Resized image result"]

        tool = HuggingFaceVisualizerTool()
        result = tool.forward("large_image.jpg", "What's this?")

        assert result == "Resized image result"
        mock_resize.assert_called_once_with("large_image.jpg")
        assert mock_process.call_count == 2


class TestOpenAIVisualizerTool:
    """Test the OpenAIVisualizerTool class."""

    def test_initialization_with_api_key(self):
        """Test OpenAIVisualizerTool initialization with API key."""
        tool = OpenAIVisualizerTool(api_key="test_key")

        assert tool.name == "openai_visualizer"
        assert "answer questions about attached images" in tool.description
        assert tool.api_key == "test_key"
        assert tool.model == "gpt-4o"  # Default model

    def test_initialization_without_api_key_raises_error(self):
        """Test OpenAIVisualizerTool initialization without API key raises error."""
        with patch.dict(os.environ, {}, clear=True), pytest.raises(ValueError, match="OpenAI API key is required"):
            OpenAIVisualizerTool()

    def test_invalid_image_path_type(self):
        """Test OpenAIVisualizerTool with invalid image path type."""
        tool = OpenAIVisualizerTool(api_key="test_key")

        with pytest.raises(TypeError, match="You should provide at least"):
            tool.forward(None)

    @patch("requests.post")
    @patch("mxgo.scripts.visual_qa.encode_image")
    def test_forward_success(self, mock_encode, mock_post):
        """Test successful OpenAI API call."""
        mock_encode.return_value = "base64_image_data"

        mock_response = Mock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "OpenAI analysis result"}}]}
        mock_post.return_value = mock_response

        tool = OpenAIVisualizerTool(api_key="test_key")
        result = tool.forward("test_image.jpg", "Analyze this image")

        assert result == "OpenAI analysis result"
        mock_encode.assert_called_once_with("test_image.jpg")
        mock_post.assert_called_once()

    @patch("requests.post")
    @patch("mxgo.scripts.visual_qa.encode_image")
    def test_forward_without_question(self, mock_encode, mock_post):
        """Test OpenAI tool without specific question."""
        mock_encode.return_value = "base64_data"

        mock_response = Mock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "Default caption"}}]}
        mock_post.return_value = mock_response

        tool = OpenAIVisualizerTool(api_key="test_key")
        result = tool.forward("image.jpg")

        assert "You did not provide a particular question" in result
        assert "detailed caption for the image" in result

    @patch("requests.post")
    @patch("mxgo.scripts.visual_qa.encode_image")
    def test_forward_api_error(self, mock_encode, mock_post):
        """Test OpenAI tool handling API errors."""
        mock_encode.return_value = "base64_data"
        mock_post.return_value.json.return_value = {"error": "API Error"}

        tool = OpenAIVisualizerTool(api_key="test_key")

        with pytest.raises(ValueError, match="Response format unexpected"):
            tool.forward("image.jpg", "What's this?")


class TestAzureVisualizerTool:
    """Test the AzureVisualizerTool class."""

    def test_initialization(self):
        """Test AzureVisualizerTool initialization."""
        mock_model = Mock()
        tool = AzureVisualizerTool(model=mock_model)

        assert tool.name == "azure_visualizer"
        assert "answer questions about attached images" in tool.description
        assert tool.model == mock_model

    @patch("mxgo.scripts.visual_qa.encode_image")
    def test_forward_success(self, mock_encode):
        """Test successful Azure OpenAI image analysis."""
        mock_encode.return_value = "base64_image_data"

        mock_model = Mock()
        mock_response = Mock()
        mock_response.content = "Azure analysis result"
        mock_model.return_value = mock_response

        tool = AzureVisualizerTool(model=mock_model)
        result = tool.forward("test_image.jpg", "Analyze this image")

        assert result == "Azure analysis result"
        mock_encode.assert_called_once_with("test_image.jpg")
        mock_model.assert_called_once()

        # Check the model was called with correct parameters
        call_args = mock_model.call_args
        messages = call_args[0][0]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert len(messages[0]["content"]) == 2
        assert messages[0]["content"][0]["type"] == "text"
        assert messages[0]["content"][1]["type"] == "image_url"

    @patch("mxgo.scripts.visual_qa.encode_image")
    def test_forward_without_question(self, mock_encode):
        """Test Azure visualizer without specific question."""
        mock_encode.return_value = "base64_data"

        mock_model = Mock()
        mock_response = Mock()
        mock_response.content = "Default caption"
        mock_model.return_value = mock_response

        tool = AzureVisualizerTool(model=mock_model)
        result = tool.forward("image.jpg")

        assert "You did not provide a particular question" in result
        assert "detailed caption for the image" in result

    @patch("mxgo.scripts.visual_qa.encode_image")
    @patch("mxgo.scripts.visual_qa.resize_image")
    def test_forward_image_too_large_retry(self, mock_resize, mock_encode):
        """Test Azure visualizer handling large image errors."""
        mock_encode.return_value = "base64_data"
        mock_resize.return_value = "resized_image.jpg"

        mock_model = Mock()

        # First call fails with size error, second succeeds after resize
        mock_model.side_effect = [Exception("image too large"), Mock(content="Resized result")]

        tool = AzureVisualizerTool(model=mock_model)
        result = tool.forward("large_image.jpg", "What's this?")

        # The function successfully retries with resized image and returns the result
        assert result == "Resized result"
        mock_resize.assert_called_once_with("large_image.jpg")

    @patch("mxgo.scripts.visual_qa.encode_image")
    def test_forward_empty_response(self, mock_encode):
        """Test Azure visualizer handling empty response."""
        mock_encode.return_value = "base64_data"

        mock_model = Mock()
        mock_response = Mock()
        mock_response.content = ""
        mock_model.return_value = mock_response

        tool = AzureVisualizerTool(model=mock_model)
        result = tool.forward("image.jpg", "What's this?")

        # The function catches the exception and returns an error message
        assert "Error processing image: Empty response from Azure OpenAI" in result

    @patch("mxgo.scripts.visual_qa.encode_image")
    def test_forward_api_error(self, mock_encode):
        """Test Azure visualizer handling API errors."""
        mock_encode.return_value = "base64_data"

        mock_model = Mock()
        mock_model.side_effect = Exception("API connection failed")

        tool = AzureVisualizerTool(model=mock_model)
        result = tool.forward("image.jpg", "What's this?")

        assert "Error processing image: API connection failed" in result

    @patch("mxgo.scripts.visual_qa.encode_image")
    def test_forward_mime_type_detection(self, mock_encode):
        """Test MIME type detection for different image formats."""
        mock_encode.return_value = "base64_data"

        mock_model = Mock()
        mock_response = Mock()
        mock_response.content = "Analysis result"
        mock_model.return_value = mock_response

        tool = AzureVisualizerTool(model=mock_model)

        # Test different image extensions
        test_files = ["image.jpg", "image.png", "image.gif", "image.unknown"]

        for filename in test_files:
            result = tool.forward(filename, "Analyze")
            assert result == "Analysis result"

            # Check MIME type handling
            call_args = mock_model.call_args
            content = call_args[0][0][0]["content"][1]

            if filename.endswith(".unknown"):
                # Should default to JPEG
                assert content["image_url"]["url"].startswith("data:image/jpeg;base64,")
            else:
                # Should detect proper MIME type
                assert "data:image/" in content["image_url"]["url"]


class TestLegacyFunctions:
    """Test the legacy function-based tools for backward compatibility."""

    def test_azure_visualizer_deprecation_warning(self):
        """Test that azure_visualizer function shows deprecation warning."""
        with patch("mxgo.scripts.visual_qa.logger") as mock_logger:
            result = azure_visualizer("image.jpg", "What's this?")

            # Should log deprecation warning
            mock_logger.warning.assert_called_with(
                "azure_visualizer function is deprecated. Use AzureVisualizerTool instead."
            )
            # Should return error message
            assert "Error: azure_visualizer function is deprecated" in result

    @patch("mxgo.scripts.visual_qa.OpenAIVisualizerTool")
    def test_visualizer_backward_compatibility(self, mock_tool_class):
        """Test that visualizer function maintains backward compatibility."""
        mock_tool = Mock()
        mock_tool.forward.return_value = "Compatibility result"
        mock_tool_class.return_value = mock_tool

        with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}):
            result = visualizer("image.jpg", "What's this?")

            assert result == "Compatibility result"
            mock_tool_class.assert_called_once_with(api_key="test_key")
            mock_tool.forward.assert_called_once_with("image.jpg", "What's this?")

    def test_visualizer_no_api_key(self):
        """Test visualizer function without API key."""
        with patch.dict(os.environ, {}, clear=True):
            result = visualizer("image.jpg", "What's this?")

            assert "Error: OpenAI API key not found" in result


class TestIntegrationScenarios:
    """Test integration scenarios combining multiple visual processing components."""

    def test_huggingface_visualizer_tool_integration(self):
        """Test realistic integration of HuggingFaceVisualizerTool with error handling."""
        tool = HuggingFaceVisualizerTool()

        # Create a real test image
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            img = Image.new("RGB", (100, 100), color="red")
            img.save(temp_file.name, "JPEG")
            temp_path = temp_file.name

        try:
            with patch("mxgo.scripts.visual_qa.process_images_and_text") as mock_process:
                mock_process.return_value = "Integration test result"

                result = tool.forward(temp_path, "What color is this image?")

                # Should return the processed result
                assert result == "Integration test result"
                mock_process.assert_called_once_with(temp_path, "What color is this image?", tool.client)

        finally:
            Path(temp_path).unlink()

    def test_azure_visualizer_tool_integration(self):
        """Test realistic integration of AzureVisualizerTool with error handling."""
        mock_model = Mock()
        mock_response = Mock()
        mock_response.content = "Azure integration result"
        mock_model.return_value = mock_response

        tool = AzureVisualizerTool(model=mock_model)

        # Create a real test image
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_file:
            img = Image.new("RGB", (100, 100), color="blue")
            img.save(temp_file.name, "JPEG")
            temp_path = temp_file.name

        try:
            result = tool.forward(temp_path, "What color is this image?")

            # Should return the processed result
            assert result == "Azure integration result"
            mock_model.assert_called_once()

        finally:
            Path(temp_path).unlink()

    def test_error_handling_chain(self):
        """Test error handling across different visual processing functions."""
        # Test that errors propagate properly through the processing chain
        with pytest.raises(FileNotFoundError):
            encode_image("nonexistent_file.jpg")

        with pytest.raises(FileNotFoundError):
            resize_image("nonexistent_file.jpg")

        # Test deprecated function error
        result = azure_visualizer("image.jpg")
        assert "Error: azure_visualizer function is deprecated" in result
