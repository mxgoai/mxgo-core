import os
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote

# Add email parsing imports for .eml support
from email import policy
from email.parser import BytesParser
import re
import uuid
import shutil

from smolagents import Tool
from smolagents.models import MessageRole, Model

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mdconvert import MarkdownConverter

from mxtoai._logging import get_logger

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
    - Email files (.eml format) - extracts headers, body, and attachment metadata
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

    def __init__(self, model: Optional[Model] = None):
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

    def _process_eml_file(self, file_path: Path, extract_attachments: bool = True) -> tuple[str, list[dict[str, Any]]]:
        """
        Process .eml email files to extract content and metadata, optionally extracting nested attachments.

        Args:
            file_path: Path to the .eml file.
            extract_attachments: Whether to extract and save attachments from the email.

        Returns:
            tuple: (email_content_text, list_of_extracted_attachments)

        """
        try:
            with open(file_path, "rb") as fp:
                msg = BytesParser(policy=policy.default).parse(fp)

            # Extract metadata
            metadata = {
                "subject": msg.get("subject", ""),
                "from": msg.get("from", ""),
                "to": msg.get("to", ""),
                "date": msg.get("date", ""),
                "cc": msg.get("cc", ""),
                "bcc": msg.get("bcc", ""),
            }

            # Extract body content
            body_text = self._extract_email_body(msg)

            # Extract and optionally save attachments
            extracted_attachments = []
            attachment_info = []

            if extract_attachments:
                extracted_attachments = self._extract_and_save_email_attachments(msg, file_path)
                attachment_info = [
                    {
                        "filename": att["filename"],
                        "content_type": att["content_type"],
                        "size": att["size"]
                    } for att in extracted_attachments
                ]
            else:
                attachment_info = self._extract_email_attachment_info(msg)

            # Format the extracted content
            content_parts = []
            content_parts.append("=== EMAIL MESSAGE ===")
            content_parts.append(f"Subject: {metadata['subject']}")
            content_parts.append(f"From: {metadata['from']}")
            content_parts.append(f"To: {metadata['to']}")
            content_parts.append(f"Date: {metadata['date']}")
            if metadata['cc']:
                content_parts.append(f"CC: {metadata['cc']}")
            if metadata['bcc']:
                content_parts.append(f"BCC: {metadata['bcc']}")

            content_parts.append("\n=== EMAIL BODY ===")
            content_parts.append(body_text)

            if attachment_info:
                if extract_attachments:
                    content_parts.append("\n=== EXTRACTED ATTACHMENTS ===")
                    for att in attachment_info:
                        content_parts.append(f"- {att['filename']} ({att['content_type']}, {att['size']} bytes) [EXTRACTED FOR PROCESSING]")
                else:
                    content_parts.append("\n=== ATTACHMENTS IN EMAIL ===")
                    for att in attachment_info:
                        content_parts.append(f"- {att['filename']} ({att['content_type']}, {att['size']} bytes)")

            email_content = "\n".join(content_parts)
            return email_content, extracted_attachments

        except Exception as e:
            logger.error(f"Error processing .eml file {file_path}: {e!s}")
            raise

    def _extract_and_save_email_attachments(self, msg, original_eml_path: Path) -> list[dict[str, Any]]:
        """
        Extract attachments from an email message and save them to disk.

        Args:
            msg: Email message object from the email library.
            original_eml_path: Path to the original .eml file (used for creating subdirectory).

        Returns:
            list[dict[str, Any]]: List of extracted attachment metadata with file paths.

        """
        extracted_attachments = []

        if not msg.is_multipart():
            return extracted_attachments

        # Create a subdirectory for extracted attachments
        eml_name = original_eml_path.stem
        extraction_dir = self.attachments_dir / f"{eml_name}_extracted_{uuid.uuid4().hex[:8]}"
        extraction_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Extracting attachments from {original_eml_path.name} to {extraction_dir}")

        for part in msg.iter_parts():
            filename = part.get_filename()
            if filename:
                try:
                    content_type = part.get_content_type()
                    payload = part.get_payload(decode=True)

                    if payload:
                        # Clean the filename for filesystem safety
                        safe_filename = self._sanitize_filename(filename)
                        attachment_path = extraction_dir / safe_filename

                        # Write the attachment to disk
                        with open(attachment_path, "wb") as f:
                            f.write(payload)

                        extracted_attachments.append({
                            "filename": safe_filename,
                            "original_filename": filename,
                            "content_type": content_type,
                            "size": len(payload),
                            "path": str(attachment_path),
                            "extracted_from_eml": str(original_eml_path)
                        })

                        logger.info(f"Extracted attachment: {safe_filename} ({content_type}, {len(payload)} bytes)")

                except Exception as e:
                    logger.error(f"Error extracting attachment '{filename}': {e!s}")
                    continue

        return extracted_attachments

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize a filename for safe filesystem storage.

        Args:
            filename: Original filename.

        Returns:
            str: Sanitized filename safe for filesystem.

        """
        # Remove or replace dangerous characters
        unsafe_chars = '<>:"/\\|?*'
        for char in unsafe_chars:
            filename = filename.replace(char, '_')

        # Limit length and ensure it's not empty
        filename = filename[:255] if len(filename) > 255 else filename
        return filename if filename else f"unnamed_attachment_{uuid.uuid4().hex[:8]}"

    def _extract_email_body(self, msg) -> str:
        """
        Extract the body content from an email message.
        Handles nested multipart structures (e.g., multipart/mixed -> multipart/alternative).

        Args:
            msg: Email message object from the email library.

        Returns:
            str: The email body as plain text.

        """
        body = ""

        def extract_content_from_part(part):
            """Helper function to extract content from a single part"""
            try:
                # First try the standard method
                content = part.get_content()
                if content and content.strip():
                    return content.strip()
            except Exception as e:
                logger.debug(f"get_content() failed: {e}")

            # Fallback: try manual payload decoding for base64 content
            try:
                payload = part.get_payload(decode=True)
                if payload:
                    content = payload.decode('utf-8', errors='ignore')
                    if content and content.strip():
                        return content.strip()
            except Exception as e:
                logger.debug(f"Manual payload decoding failed: {e}")

            return None

        def find_text_content(part, prefer_plain=True):
            """Recursively find text content in nested multipart structures"""

            if not part.is_multipart():
                # This is a leaf part - check if it's what we want
                content_type = part.get_content_type()
                content_disposition = part.get("Content-Disposition", "")

                # Skip attachments
                if "attachment" in content_disposition.lower():
                    return None

                if content_type == "text/plain":
                    content = extract_content_from_part(part)
                    if content:
                        return content
                elif content_type == "text/html":
                    content = extract_content_from_part(part)
                    if content:
                        return self._html_to_text(content)
            else:
                # This is a multipart - recurse into it
                text_content = None
                html_content = None

                for nested_part in part.iter_parts():
                    nested_result = find_text_content(nested_part, prefer_plain)
                    if nested_result:
                        nested_content_type = nested_part.get_content_type()

                        # If we got a result from a nested part, determine what type it is
                        # For multipart parts, we need to check what was actually returned
                        if nested_part.is_multipart():
                            # This is content from a nested multipart - treat as text
                            if not text_content:
                                text_content = nested_result
                        else:
                            # This is a direct content part
                            if nested_content_type == "text/plain":
                                text_content = nested_result
                                # If we prefer plain text and found it, use it immediately
                                if prefer_plain:
                                    return text_content
                            elif nested_content_type == "text/html" and not text_content:
                                html_content = nested_result

                # Return the best content we found
                return text_content or html_content

            return None

        if msg.is_multipart():
            body = find_text_content(msg, prefer_plain=True)
        else:
            # Non-multipart message
            content_type = msg.get_content_type()
            if content_type == "text/plain":
                body = extract_content_from_part(msg)
            elif content_type == "text/html":
                content = extract_content_from_part(msg)
                if content:
                    body = self._html_to_text(content)

        return body if body else "No readable content found in email body."

    def _html_to_text(self, html: str) -> str:
        """
        Convert HTML to plain text using simple regex.

        Args:
            html: HTML content.

        Returns:
            str: Plain text version of the HTML.

        """
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Normalize whitespace
        return re.sub(r"\s+", " ", text).strip()

    def _extract_email_attachment_info(self, msg) -> list[dict[str, Any]]:
        """
        Extract attachment information from an email message without saving files.

        Args:
            msg: Email message object from the email library.

        Returns:
            list[dict[str, Any]]: List of attachment metadata.

        """
        attachments = []

        if msg.is_multipart():
            for part in msg.iter_parts():
                filename = part.get_filename()
                if filename:
                    content_type = part.get_content_type()
                    # Get payload size (approximate)
                    payload = part.get_payload(decode=True)
                    size = len(payload) if payload else 0

                    attachments.append({
                        "filename": filename,
                        "content_type": content_type,
                        "size": size
                    })

        return attachments

    def _process_document(self, file_path: Path) -> str:
        """
        Process document using MarkdownConverter or .eml processor.

        Args:
            file_path: Path to the document file.

        Returns:
            str: The text content extracted from the document.

        """
        try:
            # Check if this is an .eml file
            if file_path.suffix.lower() == '.eml':
                email_content, _ = self._process_eml_file(file_path, extract_attachments=False)
                return email_content

            # Use existing MarkdownConverter for other document types
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
        Process email attachments synchronously, with support for nested attachment extraction.

        Args:
            attachments: List of attachment dictionaries containing file information.
            mode: Processing mode: 'basic' for metadata only, 'full' for complete content analysis.

        Returns:
            dict: Processed attachments with content and summaries.

        """
        processed_attachments = []
        nested_attachments_to_process = []

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

                # Skip image files - they should be handled by azure_visualizer directly
                if attachment["type"].startswith("image/"):
                    processed_attachments.append(
                        {
                            **attachment,
                            "content": {
                                "text": "This is an image file that requires visual processing.",
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

                # Special handling for .eml files - extract nested attachments
                if attachment["filename"].lower().endswith('.eml') or attachment["type"] in ["message/rfc822", "application/x-eml"]:
                    try:
                        email_content, extracted_attachments = self._process_eml_file(resolved_path, extract_attachments=True)

                        # Add the .eml file processing result
                        processed_attachments.append(
                            {
                                **attachment,
                                "content": {
                                    "text": email_content[: self.text_limit] if len(email_content) > self.text_limit else email_content,
                                    "type": "text",
                                    "summary": None,
                                    "extracted_attachments_count": len(extracted_attachments)
                                },
                            }
                        )

                        # Queue extracted attachments for processing
                        for extracted_att in extracted_attachments:
                            nested_attachments_to_process.append({
                                "filename": extracted_att["filename"],
                                "type": extracted_att["content_type"],
                                "path": extracted_att["path"],
                                "size": extracted_att["size"],
                                "extracted_from": attachment["filename"]
                            })

                        logger.info(f"Successfully processed .eml file: {attachment['filename']} with {len(extracted_attachments)} extracted attachments")

                    except Exception as e:
                        logger.error(f"Error processing .eml file {attachment['filename']}: {e!s}")
                        processed_attachments.append({**attachment, "error": f"EML processing error: {e!s}"})
                        continue
                else:
                    # Process non-image, non-eml attachments normally
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
                            "content": {
                                "text": content[: self.text_limit] if len(content) > self.text_limit else content,
                                "type": "text",
                                "summary": summary,
                            },
                        }
                    )
                    logger.info(f"Successfully processed: {attachment['filename']}")

            except Exception as e:
                logger.error(f"Error processing attachment {attachment.get('filename', 'unknown')}: {e!s}")
                processed_attachments.append(
                    {**{k: v for k, v in attachment.items() if k in ["filename", "type", "size"]}, "error": str(e)}
                )

        # Process nested attachments recursively (if any were extracted from .eml files)
        if nested_attachments_to_process:
            logger.info(f"Processing {len(nested_attachments_to_process)} nested attachments extracted from .eml files")
            nested_results = self.forward(nested_attachments_to_process, mode)

            # Add nested results to the main results with special marking
            for nested_att in nested_results["attachments"]:
                nested_att["is_nested_attachment"] = True
                processed_attachments.append(nested_att)

        return {"attachments": processed_attachments, "summary": self._create_attachment_summary(processed_attachments)}

    def _create_attachment_summary(self, attachments: list[dict[str, Any]]) -> str:
        """
        Create a summary of processed attachments, including nested attachments.

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
        nested = 0
        eml_files = 0

        for att in attachments:
            if att.get("is_nested_attachment"):
                nested += 1

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

                    # Special handling for .eml files
                    if att['filename'].lower().endswith('.eml'):
                        eml_files += 1
                        extracted_count = content.get("extracted_attachments_count", 0)
                        summary_parts.append(f"Email: {att['filename']} (extracted {extracted_count} attachments)")
                    elif att.get("is_nested_attachment"):
                        summary_parts.append(f"Nested attachment: {att['filename']} (from {att.get('extracted_from', 'unknown')})")
                    else:
                        summary_parts.append(f"Document: {att['filename']}")

                    if content.get("summary"):
                        summary_parts.append(f"Summary: {content['summary']}")
                    else:
                        text = content.get("text", "")
                        preview = text[:200] + "..." if len(text) > 200 else text
                        summary_parts.append(f"Preview: {preview}")

        status_parts = []
        if successful > 0:
            status_parts.append(f"{successful} documents")
        if eml_files > 0:
            status_parts.append(f"{eml_files} email files")
        if nested > 0:
            status_parts.append(f"{nested} nested attachments")
        if images > 0:
            status_parts.append(f"{images} images pending visual processing")
        if failed > 0:
            status_parts.append(f"{failed} failed")

        status = f"Processed {', '.join(status_parts)}" if status_parts else "No attachments processed"

        return status + "\n\n" + "\n\n".join(summary_parts)
