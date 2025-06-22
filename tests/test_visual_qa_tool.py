import io
from unittest.mock import Mock, patch

from PIL import Image

from mxtoai.tools.visual_qa_tool import VisualQATool


class TestVisualQATool:
    """Test the VisualQATool class integration with attachment service."""

    def test_initialization(self):
        """Test VisualQATool initialization."""
        tool = VisualQATool()

        assert tool.name == "visual_qa"
        assert "Answer questions about image attachments" in tool.description
        assert "filename" in tool.inputs
        assert "question" in tool.inputs
        assert "use_azure" in tool.inputs
        assert tool.output_type == "string"

    def test_no_attachment_service(self):
        """Test error when no attachment service is available."""
        tool = VisualQATool()  # No context provided

        result = tool.forward("test.jpg", "What is this?")

        assert "Error: No attachment service available" in result

    def test_attachment_not_found(self):
        """Test error when attachment is not found."""
        # Mock context with attachment service
        mock_context = Mock()
        mock_attachment_service = Mock()
        mock_attachment_service.has_attachment.return_value = False
        mock_context.attachment_service = mock_attachment_service

        tool = VisualQATool(context=mock_context)

        result = tool.forward("nonexistent.jpg", "What is this?")

        assert "Error: Attachment 'nonexistent.jpg' not found" in result

    @patch("mxtoai.tools.visual_qa_tool.azure_visualizer_from_content")
    def test_successful_azure_processing(self, mock_azure_visualizer):
        """Test successful image processing with Azure OpenAI."""
        mock_azure_visualizer.return_value = "This is a test image showing a red square."

        # Create a simple test image in memory
        img = Image.new("RGB", (100, 100), color="red")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        content = img_bytes.getvalue()

        # Mock context with attachment service
        mock_context = Mock()
        mock_attachment_service = Mock()
        mock_attachment_service.has_attachment.return_value = True
        mock_attachment_service.get_content.return_value = content
        mock_attachment_service.get_metadata.return_value = {"type": "image/jpeg", "size": len(content)}
        mock_context.attachment_service = mock_attachment_service

        tool = VisualQATool(context=mock_context)

        result = tool.forward("test.jpg", "What color is this?", use_azure=True)

        assert "This is a test image showing a red square." in result
        mock_azure_visualizer.assert_called_once_with(content, "image/jpeg", "What color is this?")

    @patch("mxtoai.tools.visual_qa_tool.visualizer_from_content")
    def test_successful_openai_processing(self, mock_visualizer):
        """Test successful image processing with standard OpenAI."""
        mock_visualizer.return_value = "This is a test image showing a blue circle."

        # Create a simple test image in memory
        img = Image.new("RGB", (100, 100), color="blue")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="PNG")
        content = img_bytes.getvalue()

        # Mock context with attachment service
        mock_context = Mock()
        mock_attachment_service = Mock()
        mock_attachment_service.has_attachment.return_value = True
        mock_attachment_service.get_content.return_value = content
        mock_attachment_service.get_metadata.return_value = {"type": "image/png", "size": len(content)}
        mock_context.attachment_service = mock_attachment_service

        tool = VisualQATool(context=mock_context)

        result = tool.forward("test.png", "What shape is this?", use_azure=False)

        assert "This is a test image showing a blue circle." in result
        mock_visualizer.assert_called_once_with(content, "image/png", "What shape is this?")

    def test_non_image_file(self):
        """Test error when trying to process non-image file."""
        # Mock context with attachment service returning a text file
        mock_context = Mock()
        mock_attachment_service = Mock()
        mock_attachment_service.has_attachment.return_value = True
        mock_attachment_service.get_content.return_value = b"This is text content"
        mock_attachment_service.get_metadata.return_value = {"type": "text/plain", "size": 20}
        mock_context.attachment_service = mock_attachment_service

        tool = VisualQATool(context=mock_context)

        result = tool.forward("document.txt", "What is this?")

        assert "is not an image file" in result

    def test_mime_type_detection(self):
        """Test MIME type detection for files without proper metadata."""
        # Create a simple test image
        img = Image.new("RGB", (50, 50), color="green")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        content = img_bytes.getvalue()

        # Mock context with attachment service - no type in metadata
        mock_context = Mock()
        mock_attachment_service = Mock()
        mock_attachment_service.has_attachment.return_value = True
        mock_attachment_service.get_content.return_value = content
        mock_attachment_service.get_metadata.return_value = {"size": len(content)}  # No type field
        mock_context.attachment_service = mock_attachment_service

        with patch("mxtoai.tools.visual_qa_tool.azure_visualizer_from_content") as mock_azure:
            mock_azure.return_value = "Green square detected"

            tool = VisualQATool(context=mock_context)
            result = tool.forward("image.jpg", "What color?")

            assert "Green square detected" in result
            # Should detect JPEG from filename
            mock_azure.assert_called_once_with(content, "image/jpeg", "What color?")

    @patch("mxtoai.tools.visual_qa_tool.azure_visualizer_from_content")
    def test_processing_exception_handling(self, mock_azure_visualizer):
        """Test error handling when image processing fails."""
        mock_azure_visualizer.side_effect = Exception("API error")

        # Create test image
        img = Image.new("RGB", (100, 100), color="red")
        img_bytes = io.BytesIO()
        img.save(img_bytes, format="JPEG")
        content = img_bytes.getvalue()

        # Mock context
        mock_context = Mock()
        mock_attachment_service = Mock()
        mock_attachment_service.has_attachment.return_value = True
        mock_attachment_service.get_content.return_value = content
        mock_attachment_service.get_metadata.return_value = {"type": "image/jpeg", "size": len(content)}
        mock_context.attachment_service = mock_attachment_service

        tool = VisualQATool(context=mock_context)

        result = tool.forward("test.jpg", "What is this?")

        assert "Error processing image 'test.jpg': API error" in result

    def test_content_retrieval_failure(self):
        """Test error when content cannot be retrieved."""
        # Mock context with attachment service that can't retrieve content
        mock_context = Mock()
        mock_attachment_service = Mock()
        mock_attachment_service.has_attachment.return_value = True
        mock_attachment_service.get_content.return_value = None  # Content retrieval fails
        mock_context.attachment_service = mock_attachment_service

        tool = VisualQATool(context=mock_context)

        result = tool.forward("test.jpg", "What is this?")

        assert "Error: Could not retrieve content for 'test.jpg'" in result

    def test_metadata_retrieval_failure(self):
        """Test error when metadata cannot be retrieved."""
        # Mock context with attachment service that can't retrieve metadata
        mock_context = Mock()
        mock_attachment_service = Mock()
        mock_attachment_service.has_attachment.return_value = True
        mock_attachment_service.get_content.return_value = b"image_content"
        mock_attachment_service.get_metadata.return_value = None  # Metadata retrieval fails
        mock_context.attachment_service = mock_attachment_service

        tool = VisualQATool(context=mock_context)

        result = tool.forward("test.jpg", "What is this?")

        assert "Error: Could not retrieve metadata for 'test.jpg'" in result
