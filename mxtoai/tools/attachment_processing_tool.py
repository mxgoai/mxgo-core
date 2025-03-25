import os
import json
import mimetypes
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
import logging
from smolagents import Tool
from smolagents.models import MessageRole, Model

# Import needed converters
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.mdconvert import MarkdownConverter

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("attachment_tool")

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
                    "size": {"type": "integer", "description": "Size of the file in bytes"}
                }
            }
        },
        "mode": {
            "type": "string",
            "description": "Processing mode: 'basic' for metadata only, 'full' for complete content analysis",
            "enum": ["basic", "full"],
            "default": "basic",
            "nullable": True
        }
    }
    output_type = "object"
    
    def __init__(self, model: Optional[Model] = None):
        super().__init__()
        self.md_converter = MarkdownConverter()
        self.model = model
        self.text_limit = 8000
        
        # Set up attachments directory path
        self.attachments_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "attachments"))
        os.makedirs(self.attachments_dir, exist_ok=True)
    
    def _validate_attachment_path(self, file_path: str) -> str:
        """Validate and resolve the attachment file path."""
        try:
            file_path = file_path.strip('"\'')
            abs_path = os.path.abspath(file_path)
            
            # Check if file exists at the exact path
            if os.path.isfile(abs_path):
                return abs_path
                
            # Try URL decoding if needed
            from urllib.parse import unquote
            decoded_path = unquote(abs_path)
            if os.path.isfile(decoded_path):
                return decoded_path
            
            raise FileNotFoundError(f"File not found: {file_path}")
            
        except Exception as e:
            logger.error(f"Error validating path {file_path}: {str(e)}")
            raise
    
    def _process_document(self, file_path: str) -> str:
        """Process document using MarkdownConverter."""
        try:
            result = self.md_converter.convert(file_path)
            if not result or not hasattr(result, 'text_content'):
                raise ValueError(f"Failed to convert document: {file_path}")
            return result.text_content
        except Exception as e:
            logger.error(f"Error converting document {file_path}: {str(e)}")
            raise
    
    def forward(self, attachments: List[Dict[str, Any]], mode: str = "basic") -> Dict[str, Any]:
        """Process email attachments synchronously."""
        processed_attachments = []
        logger.info(f"Processing {len(attachments)} attachments in {mode} mode")
        
        for attachment in attachments:
            try:
                # Validate required fields
                if not all(key in attachment for key in ["filename", "type", "path", "size"]):
                    raise ValueError(f"Missing required fields in attachment: {attachment}")
                
                logger.info(f"Processing attachment: {attachment['filename']}")
                file_path = attachment.get("path", "")
                
                try:
                    # Check if file exists before proceeding
                    if not os.path.isfile(file_path):
                        raise FileNotFoundError(f"File does not exist: {file_path}")
                        
                    resolved_path = self._validate_attachment_path(file_path)
                    attachment["path"] = resolved_path
                    
                    # Skip image files - they should be handled by azure_visualizer directly
                    if attachment["type"].startswith("image/"):
                        processed_attachments.append({
                            **attachment,
                            "content": {
                                "text": "This is an image file. Please use the azure_visualizer tool directly with the following path: " + resolved_path,
                                "type": "image",
                                "requires_visual_qa": True
                            }
                        })
                        logger.info(f"Skipped image file: {attachment['filename']} - use azure_visualizer tool instead")
                        continue
                    
                    # Process non-image attachments
                    content = self._process_document(resolved_path)
                    
                    # If in full mode and model is available, generate a summary
                    summary = None
                    if mode == "full" and self.model and len(content) > 4000:
                        messages = [
                            {
                                "role": MessageRole.SYSTEM,
                                "content": [{"type": "text", "text": f"Here is a file:\n### {attachment['filename']}\n\n{content[:self.text_limit]}"}]
                            },
                            {
                                "role": MessageRole.USER,
                                "content": [{"type": "text", "text": "Please provide a comprehensive summary of this document in 5-7 sentences."}]
                            }
                        ]
                        summary = self.model(messages).content
                    
                    processed_attachments.append({
                        **attachment,
                        "content": {
                            "text": content[:self.text_limit] if len(content) > self.text_limit else content,
                            "type": "text",
                            "summary": summary
                        }
                    })
                    logger.info(f"Successfully processed: {attachment['filename']}")
                    
                except FileNotFoundError as e:
                    logger.error(f"File not found: {file_path}")
                    processed_attachments.append({
                        "filename": attachment.get("filename", "unknown"),
                        "error": str(e)
                    })
                    
            except Exception as e:
                logger.error(f"Error processing attachment {attachment.get('filename', 'unknown')}: {str(e)}")
                processed_attachments.append({
                    "filename": attachment.get("filename", "unknown"),
                    "error": str(e)
                })
        
        return {
            "attachments": processed_attachments,
            "summary": self._create_attachment_summary(processed_attachments)
        }
        
    def _create_attachment_summary(self, attachments: List[Dict[str, Any]]) -> str:
        """Create a summary of processed attachments."""
        if not attachments:
            return "No attachments processed."
            
        summary_parts = []
        for att in attachments:
            if "error" in att:
                summary_parts.append(f"Failed to process {att['filename']}: {att['error']}")
                continue
                
            content = att.get("content", {})
            if content:
                if content.get("type") == "image":
                    summary_parts.append(f"Image {att['filename']}: Use azure_visualizer with path: {att['path']}")
                elif content.get("type") == "text":
                    summary_parts.append(f"Document: {att['filename']}")
                    if content.get("summary"):
                        summary_parts.append(f"Summary: {content['summary']}")
                    else:
                        text = content.get("text", "")
                        preview = text[:200] + "..." if len(text) > 200 else text
                        summary_parts.append(f"Preview: {preview}")
            else:
                summary_parts.append(f"Basic info for {att['filename']} ({att.get('type', 'unknown type')})")
        
        return "\n\n".join(summary_parts) 