import os

from smolagents import Tool

from mxtoai._logging import get_logger
from mxtoai.scripts.mdconvert import MarkdownConverter

logger = get_logger(__name__)


class AttachmentProcessingTool(Tool):
    """
    Tool for processing email attachments from memory.
    """

    name = "attachment_processing"
    description = "Process attachments from memory and convert them to text format"
    inputs = {
        "filename": {
            "description": "Name of the attachment file to process",
            "type": "string",
        },
        "type": {
            "description": "MIME type of the attachment",
            "type": "string",
        },
        "size": {
            "description": "Size of the attachment in bytes",
            "type": "integer",
        },
    }
    output_type = "string"

    def __init__(self, context=None):
        super().__init__()
        self.converter = MarkdownConverter()
        self.context = context

    def forward(self, filename: str, type: str, size: int) -> str:
        """
        Process attachment content from memory and return text representation.

        Args:
            filename: Name of the attachment file
            type: MIME type of the attachment
            size: Size of the attachment in bytes

        Returns:
            str: Processed text content or error message

        """
        try:
            if not self.context or not self.context.attachment_service:
                return "Error: No attachment service available in request context"

            if not self.context.attachment_service.has_attachment(filename):
                return f"Error: Attachment '{filename}' not found"

            content = self.context.attachment_service.get_content(filename)
            if content is None:
                return f"Error: Could not retrieve content for '{filename}'"

            processed_content = self._process_content_from_memory(content, filename, type)

            logger.info(f"Successfully processed attachment '{filename}' from memory")
            return f"Processed attachment '{filename}':\n\n{processed_content}"

        except Exception as e:
            logger.error(f"Error processing attachment '{filename}': {e!s}")
            return f"Error processing attachment '{filename}': {e!s}"

    def _process_content_from_memory(self, content: bytes, filename: str, content_type: str) -> str:
        """
        Process file content directly from memory bytes.

        Args:
            content: Raw file content as bytes
            filename: Name of the file for context
            content_type: MIME type of the file

        Returns:
            str: Processed text content

        Raises:
            ValueError: If processing fails

        """
        try:
            if content_type.startswith("text/"):
                try:
                    return content.decode("utf-8")
                except UnicodeDecodeError:
                    return content.decode("utf-8", errors="ignore")

            _, file_extension = os.path.splitext(filename)

            result = self.converter.convert_content(content=content, filename=filename, file_extension=file_extension)

            return result.text_content

        except Exception as e:
            logger.error(f"Error processing content from memory for {filename}: {e!s}")
            msg = f"Failed to process content: {e!s}"
            raise ValueError(msg)
