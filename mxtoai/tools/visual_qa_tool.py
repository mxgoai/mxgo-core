import mimetypes
from typing import Optional

from smolagents import Tool

from mxtoai._logging import get_logger
from mxtoai.scripts.visual_qa import azure_visualizer_from_content, visualizer_from_content

logger = get_logger(__name__)


class VisualQATool(Tool):
    """
    Tool for processing image attachments from memory using visual QA.
    """

    name = "visual_qa"
    description = "Answer questions about image attachments from memory content"
    inputs = {
        "filename": {
            "description": "Name of the image attachment to analyze",
            "type": "string",
        },
        "question": {
            "description": "Question to ask about the image (optional - will provide caption if not specified)",
            "type": "string",
            "nullable": True,
        },
        "use_azure": {
            "description": "Whether to use Azure OpenAI (true) or standard OpenAI (false)",
            "type": "boolean",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, context=None):
        super().__init__()
        self.context = context

    def forward(self, filename: str, question: Optional[str] = None, use_azure: Optional[bool] = None) -> str:
        """
        Analyze an image attachment and answer questions about it.

        Args:
            filename: Name of the image attachment
            question: Question to ask about the image (optional)
            use_azure: Whether to use Azure OpenAI (defaults to True)

        Returns:
            str: Analysis result or error message

        """
        try:
            if not self.context or not self.context.attachment_service:
                return "Error: No attachment service available in request context"

            if not self.context.attachment_service.has_attachment(filename):
                return f"Error: Attachment '{filename}' not found"

            content = self.context.attachment_service.get_content(filename)
            if content is None:
                return f"Error: Could not retrieve content for '{filename}'"

            metadata = self.context.attachment_service.get_metadata(filename)
            if not metadata:
                return f"Error: Could not retrieve metadata for '{filename}'"

            mime_type = metadata.get("type", "image/jpeg")

            # Check if it's an image file
            if not mime_type.startswith("image/"):
                guessed_type, _ = mimetypes.guess_type(filename)
                if not guessed_type or not guessed_type.startswith("image/"):
                    return f"Error: '{filename}' is not an image file (type: {mime_type})"
                mime_type = guessed_type

            # Use Azure by default
            if use_azure is None:
                use_azure = True

            # Process the image
            if use_azure:
                result = azure_visualizer_from_content(content, mime_type, question)
                processing_method = "Azure OpenAI"
            else:
                result = visualizer_from_content(content, mime_type, question)
                processing_method = "OpenAI"

            logger.info(f"Successfully processed image '{filename}' using {processing_method}")
            return result

        except Exception as e:
            logger.error(f"Error processing image '{filename}': {e!s}")
            return f"Error processing image '{filename}': {e!s}"
