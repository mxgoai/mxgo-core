import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from smolagents import Tool
from smolagents.models import MessageRole, Model

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mdconvert import MarkdownConverter

from mxtoai._logging import get_logger
from mxtoai.schemas import ToolOutputWithCitations
from mxtoai.scripts.citation_manager import add_attachment_citation

# Configure logger
logger = get_logger("attachment_tool")


class AttachmentProcessingTool(Tool):
    """
    Tool for processing various types of email attachments.
    Handles documents using MarkdownConverter. For images, use the azure_visualizer tool directly.
    """

    name = "attachment_processor"
    description = """Process and analyze email attachments to extract content and insights.
    This tool can handle:
    - Documents (PDFs, Office files, text files)
    - Audio files (as transcripts)
    - HTML files
    - Markdown files

    NOTE: For image processing, please use the azure_visualizer tool directly.
    This tool will skip image files and indicate they should be processed by azure_visualizer.

    The attachments parameter should be a list of dictionaries, where each dictionary contains:
    - filename: Name of the file
    - type: MIME type
    - path: Full path to the file
    - size: File size in bytes
    """

    inputs = {
        "attachments": {
            "type": "array",
            "description": "List of attachment dictionaries containing file information. Each dictionary must have 'filename', 'type', 'path', and 'size' keys. The path must point to a file in the attachments directory.",
            "items": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Name of the file"},
                    "type": {"type": "string", "description": "MIME type or content type of the file"},
                    "path": {"type": "string", "description": "Full path to the file in the attachments directory"},
                    "size": {"type": "integer", "description": "Size of the file in bytes"},
                },
            },
        },
        "mode": {
            "type": "string",
            "description": "Processing mode: 'basic' for metadata only, 'full' for complete content analysis",
            "enum": ["basic", "full"],
            "default": "basic",
            "nullable": True,
        },
    }
    output_type = "object"

    def __init__(self, model: Model | None = None):
        """
        Initialize the attachment processing tool.

        Args:
            model: Optional model for generating summaries or processing content.

        """
        super().__init__()
        self.md_converter = MarkdownConverter()
        self.model = model
        self.text_limit = 8000

        # Set up attachments directory path
        self.attachments_dir = Path(
            os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "attachments"))
        )
        self.attachments_dir.mkdir(parents=True, exist_ok=True)

    def _validate_attachment_path(self, file_path: str) -> Path:
        """
        Validate and resolve the attachment file path.

        Args:
            file_path: Path to the attachment file.

        Returns:
            Path: The resolved file path.

        """
        try:
            if not file_path:
                msg = "Empty file path provided"
                raise ValueError(msg)

            # Clean up the path
            file_path = file_path.strip("\"'")

            # Try different path variations
            paths_to_try = [
                Path(file_path),  # Direct path
                Path(unquote(file_path)),  # URL decoded path
                self.attachments_dir / Path(file_path).name,  # Relative to attachments dir
            ]

            for path in paths_to_try:
                if path.is_file():
                    return path.resolve()

            paths_str = "\n- ".join(str(p) for p in paths_to_try)
            msg = f"File not found at any of these locations:\n- {paths_str}"
            raise FileNotFoundError(msg)

        except Exception as e:
            logger.error(f"Error validating path {file_path}: {e!s}")
            raise

    def _process_document(self, file_path: Path) -> str:
        """
        Process document using MarkdownConverter.

        Args:
            file_path: Path to the document file.

        Returns:
            str: The text content extracted from the document.

        """
        try:
            result = self.md_converter.convert(str(file_path))
            if not result or not hasattr(result, "text_content"):
                msg = f"Failed to convert document: {file_path}"
                raise ValueError(msg)
            return result.text_content
        except Exception as e:
            logger.error(f"Error converting document {file_path}: {e!s}")
            raise

    def forward(self, attachments: list[dict[str, Any]], mode: str = "basic") -> dict[str, Any]:
        """
        Process email attachments synchronously with citation tracking.

        Args:
            attachments: List of attachment dictionaries containing file information.
            mode: Processing mode: 'basic' for metadata only, 'full' for complete content analysis.

        Returns:
            str: JSON string of ToolOutputWithCitations containing processed attachments.

        """
        processed_attachments = []
        citation_ids = []
        logger.info(f"Processing {len(attachments)} attachments in {mode} mode")

        for attachment in attachments:
            try:
                # Validate required fields
                required_fields = ["filename", "type", "path", "size"]
                missing_fields = [field for field in required_fields if field not in attachment]
                if missing_fields:
                    msg = f"Missing required fields in attachment: {missing_fields}"
                    raise ValueError(msg)

                logger.info(f"Processing attachment: {attachment['filename']}")

                # Add citation for this attachment
                citation_id = add_attachment_citation(
                    attachment["filename"],
                    f"Email attachment ({attachment.get('type', 'unknown type')})"
                )
                citation_ids.append(citation_id)

                # Skip image files - they should be handled by azure_visualizer directly
                if attachment["type"].startswith("image/"):
                    processed_attachments.append(
                        {
                            **attachment,
                            "citation_id": citation_id,
                            "content": {
                                "text": f"This is an image file that requires visual processing. [#{citation_id}]",
                                "type": "image",
                                "requires_visual_qa": True,
                            },
                        }
                    )
                    logger.info(f"Skipped image file: {attachment['filename']} - use azure_visualizer tool instead")
                    continue

                # Validate and resolve the file path
                try:
                    resolved_path = self._validate_attachment_path(attachment["path"])
                    attachment["path"] = str(resolved_path)
                except FileNotFoundError as e:
                    logger.error(f"File not found: {e!s}")
                    processed_attachments.append({**attachment, "error": f"File not found: {e!s}"})
                    continue

                # Process non-image attachments
                content = self._process_document(resolved_path)

                # If in full mode and model is available, generate a summary
                summary = None
                if mode == "full" and self.model and len(content) > 4000:
                    messages = [
                        {
                            "role": MessageRole.SYSTEM,
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Here is a file:\n### {attachment['filename']}\n\n{content[: self.text_limit]}",
                                }
                            ],
                        },
                        {
                            "role": MessageRole.USER,
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Please provide a comprehensive summary of this document in 5-7 sentences.",
                                }
                            ],
                        },
                    ]
                    summary = self.model(messages).content

                processed_attachments.append(
                    {
                        **attachment,
                        "citation_id": citation_id,
                        "content": {
                            "text": f"{content[: self.text_limit] if len(content) > self.text_limit else content} [#{citation_id}]",
                            "type": "text",
                            "summary": summary,
                        },
                    }
                )
                logger.info(f"Successfully processed: {attachment['filename']}")

            except Exception as e:
                logger.error(f"Error processing attachment {attachment.get('filename', 'unknown')}: {e!s}")
                processed_attachments.append(
                    {**{k: v for k, v in attachment.items() if k in ["filename", "type", "size"]}, "citation_id": citation_id, "error": str(e)}
                )

        # Create structured output with citations
        attachment_summary = self._create_attachment_summary(processed_attachments)
        content = f"Processed {len(processed_attachments)} attachments:\n\n{attachment_summary}"

        result = ToolOutputWithCitations(
            content=content,
            metadata={
                "total_attachments": len(attachments),
                "processed_successfully": len([a for a in processed_attachments if "error" not in a]),
                "failed": len([a for a in processed_attachments if "error" in a]),
                "citation_ids": citation_ids,
                "attachments": processed_attachments
            }
        )

        return json.dumps(result.model_dump())

    def _create_attachment_summary(self, attachments: list[dict[str, Any]]) -> str:
        """
        Create a summary of processed attachments.

        Args:
            attachments: List of processed attachment dictionaries.

        Returns:
            str: Summary of processed attachments.

        """
        if not attachments:
            return "No attachments processed."

        summary_parts = []
        successful = 0
        failed = 0
        images = 0

        for att in attachments:
            if "error" in att:
                failed += 1
                summary_parts.append(f"Failed to process {att['filename']}: {att['error']}")
                continue

            content = att.get("content", {})
            if content:
                if content.get("type") == "image":
                    images += 1
                    summary_parts.append(f"Image {att['filename']}: Requires visual processing")
                elif content.get("type") == "text":
                    successful += 1
                    summary_parts.append(f"Document: {att['filename']}")
                    if content.get("summary"):
                        summary_parts.append(f"Summary: {content['summary']}")
                    else:
                        text = content.get("text", "")
                        preview = text[:200] + "..." if len(text) > 200 else text
                        summary_parts.append(f"Preview: {preview}")

        status = f"Processed {successful} documents, {images} images pending visual processing"
        if failed > 0:
            status += f", {failed} failed"

        return status + "\n\n" + "\n\n".join(summary_parts)
