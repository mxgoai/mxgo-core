import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

from smolagents import Tool
from weasyprint import CSS, HTML

from mxtoai._logging import get_logger
from mxtoai.scripts.report_formatter import ReportFormatter

logger = get_logger("pdf_export_tool")

# Constants for filename handling
MAX_FILENAME_LENGTH = 50  # Maximum length for filename before ".pdf" extension

# Constants for title extraction
MAX_TITLE_LENGTH = 100
MIN_TITLE_LENGTH = 5
MAX_SENTENCE_LENGTH = 80
MIN_SENTENCE_LENGTH = 10


class PDFExportTool(Tool):
    """Tool for exporting email content and research findings to PDF format."""

    name: ClassVar[str] = "pdf_export"
    description: ClassVar[str] = (
        "Export email content, research findings, and attachment summaries to a professionally formatted PDF document"
    )

    inputs: ClassVar[dict] = {
        "content": {
            "type": "string",
            "description": "The main content to export (email body, research findings, etc.)",
        },
        "title": {"type": "string", "description": "Title for the PDF document", "nullable": True},
        "research_findings": {
            "type": "string",
            "description": "Additional research findings to include",
            "nullable": True,
        },
        "attachments_summary": {"type": "string", "description": "Summary of processed attachments", "nullable": True},
        "include_attachments": {
            "type": "boolean",
            "description": "Whether to include attachment summaries in the PDF",
            "default": False,
            "nullable": True,
        },
    }
    output_type: ClassVar[str] = "object"

    def __init__(self):
        super().__init__()
        self.temp_dir = Path(tempfile.mkdtemp())
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.report_formatter = ReportFormatter()
        logger.debug(f"PDFExportTool initialized with temp directory: {self.temp_dir}")

    @property
    def temp_directory(self) -> Path:
        """Get the temporary directory path for external cleanup."""
        return self.temp_dir

    def __del__(self):
        """Cleanup temporary directory when object is destroyed."""
        self.cleanup()

    def cleanup(self):
        """Explicitly cleanup the temporary directory and all its contents."""
        try:
            if hasattr(self, "temp_dir") and self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
                logger.debug(f"Cleaned up PDFExportTool temp directory: {self.temp_dir}")
        except Exception as e:
            logger.warning(f"Failed to cleanup PDFExportTool temp directory: {e}")

    def forward(
        self,
        content: str,
        title: str = "Document",
        research_findings: str | None = None,
        attachments_summary: str | None = None,
        *,
        include_attachments: bool = False,
    ) -> dict[str, Any]:
        """
        Export content to PDF format.

        Args:
            content: Main content to export
            title: Document title (auto-generated if not provided)
            research_findings: Additional research content
            attachments_summary: Attachment summaries to include
            include_attachments: Whether to include attachment section

        Returns:
            Dict containing export results

        """
        try:
            # Clean and prepare content
            cleaned_content = self._clean_content(content)
            doc_title = title or self._extract_title(cleaned_content)

            # Build complete markdown document
            markdown_document = self._build_markdown_document(
                content=cleaned_content,
                title=doc_title,
                research_findings=research_findings,
                attachments_summary=attachments_summary if include_attachments else None,
            )

            # Convert to HTML using existing ReportFormatter
            html_content = self.report_formatter._to_html(markdown_document, theme="default")  # noqa: SLF001

            # Enhance HTML for PDF with custom CSS
            pdf_html = self._enhance_html_for_pdf(html_content, doc_title)

            # Generate PDF
            filename = self._sanitize_filename(doc_title) + ".pdf"
            pdf_path = self.temp_dir / filename

            HTML(string=pdf_html).write_pdf(pdf_path, stylesheets=[CSS(string=self._get_pdf_styles())])

            file_size = pdf_path.stat().st_size

            return {
                "success": True,
                "filename": filename,
                "file_path": str(pdf_path),
                "file_size": file_size,
                "mimetype": "application/pdf",
                "title": doc_title,
                "pages_estimated": max(1, len(cleaned_content) // 2000),  # Rough estimate
                "temp_dir": str(self.temp_dir),  # Include temp directory for cleanup
            }

        except Exception as e:
            logger.error(f"PDF export failed: {e}")
            return {"error": f"PDF export failed: {e!s}", "details": "Please check the content format and try again"}

    def _clean_content(self, content: str) -> str:
        """
        Clean content by removing email headers and unnecessary formatting.

        Args:
            content: Raw content to clean

        Returns:
            Cleaned content suitable for PDF export

        """
        if not content:
            return ""

        # Remove common email headers patterns
        email_header_patterns = [
            r"^From:.*$",
            r"^To:.*$",
            r"^Subject:.*$",
            r"^Date:.*$",
            r"^CC:.*$",
            r"^BCC:.*$",
            r"^Reply-To:.*$",
            r"^Message-ID:.*$",
            r"^In-Reply-To:.*$",
            r"^References:.*$",
            r"^Received:.*$",
            r"^Return-Path:.*$",
        ]

        lines = content.split("\n")
        cleaned_lines = []

        for line in lines:
            # Skip lines that match email header patterns
            is_header = any(re.match(pattern, line.strip(), re.IGNORECASE) for pattern in email_header_patterns)
            if not is_header:
                cleaned_lines.append(line)

        cleaned_content = "\n".join(cleaned_lines).strip()

        # Remove excessive whitespace but preserve paragraph breaks
        cleaned_content = re.sub(r"\n\s*\n\s*\n+", "\n\n", cleaned_content)
        return re.sub(r"[ \t]+", " ", cleaned_content)

    def _extract_title(self, content: str) -> str:
        """
        Extract a meaningful title from content.

        Args:
            content: Content to extract title from

        Returns:
            Extracted title

        """
        if not content:
            return "Document"

        # Look for markdown headers first
        lines = content.split("\n")
        for original_line in lines[:10]:  # Check first 10 lines
            line = original_line.strip()
            if line.startswith("# "):
                return line[2:].strip()[:60]  # Remove # and limit length
            if line.startswith("## "):
                return line[3:].strip()[:60]  # Remove ## and limit length

        # Look for lines that could be titles (short, meaningful lines)
        for original_line in lines[:5]:  # Check first 5 lines
            line = original_line.strip()
            if (
                line
                and len(line) < MAX_TITLE_LENGTH
                and len(line) > MIN_TITLE_LENGTH
                and not any(
                    indicator in line.lower()
                    for indicator in ["the", "this", "that", "with", "from", "email", "message"]
                )
            ):
                return line[:60]

        # Fallback: use first meaningful sentence
        sentences = re.split(r"[.!?]+", content)
        for original_sentence in sentences[:3]:
            sentence = original_sentence.strip()
            if MIN_SENTENCE_LENGTH < len(sentence) < MAX_SENTENCE_LENGTH:
                return sentence[:60]

        return f"Document - {datetime.now(timezone.utc).strftime('%B %d, %Y')}"

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename for file system compatibility.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename

        """
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', "", filename)
        filename = re.sub(r"\s+", "_", filename)
        filename = filename[:MAX_FILENAME_LENGTH]  # Limit length using constant
        return filename if filename else "document"

    def _build_markdown_document(
        self,
        content: str,
        title: str,
        research_findings: str | None = None,
        attachments_summary: str | None = None,
    ) -> str:
        """
        Build a complete markdown document for PDF conversion.

        Args:
            content: Main content
            title: Document title
            research_findings: Research content
            attachments_summary: Attachment summaries

        Returns:
            Complete markdown document

        """
        # Start with title
        markdown_parts = [f"# {title}\n"]

        # Add generation date
        markdown_parts.append(f"*Generated on {datetime.now(timezone.utc).strftime('%B %d, %Y at %I:%M %p')}*\n")

        # Add main content
        if content:
            markdown_parts.append(content)

        # Add research findings section
        if research_findings:
            markdown_parts.append("\n---\n")
            markdown_parts.append("## Research Findings\n")
            markdown_parts.append(research_findings)

        # Add attachments section
        if attachments_summary:
            markdown_parts.append("\n---\n")
            markdown_parts.append("## Attachments Summary\n")
            markdown_parts.append(attachments_summary)

        # Add professional watermark with link
        markdown_parts.append('\n\n<div class="watermark">')
        markdown_parts.append('<hr class="watermark-divider">')
        markdown_parts.append('<div class="watermark-content">')
        markdown_parts.append('<span class="watermark-text">📄 Document generated via </span>')
        markdown_parts.append('<a href="https://mxtoai.com" class="watermark-link">mxtoai.com</a>')
        markdown_parts.append('<span class="watermark-email"> • Email: </span>')
        markdown_parts.append('<a href="mailto:pdf@mxtoai.com" class="watermark-link">pdf@mxtoai.com</a>')
        markdown_parts.append("</div>")
        markdown_parts.append("</div>")

        return "\n".join(markdown_parts)

    def _enhance_html_for_pdf(self, html_content: str, title: str) -> str:
        """
        Enhance HTML content for better PDF generation.

        Args:
            html_content: HTML content from ReportFormatter
            title: Document title

        Returns:
            Enhanced HTML suitable for PDF

        """
        # Extract the body content if it's a full HTML document
        if "<body>" in html_content:
            # Extract content between body tags
            body_match = re.search(r"<body[^>]*>(.*?)</body>", html_content, re.DOTALL)
            if body_match:
                inner_html = body_match.group(1)
        else:
            inner_html = html_content

        # Create a clean PDF-optimized HTML document
        return f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="utf-8">
            <title>{self._html_escape(title)}</title>
        </head>
        <body>
            <div class="pdf-document">
                {inner_html}
            </div>
        </body>
        </html>
        """

    def _html_escape(self, text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;")
        )

    def _get_pdf_styles(self) -> str:
        """
        Get CSS styles for PDF generation.

        Returns:
            CSS stylesheet string optimized for PDF

        """
        return """
        @page {
            margin: 0.75in;
            size: letter;
            @bottom-right {
                content: "Page " counter(page) " of " counter(pages);
                font-size: 10px;
                color: #666;
                margin-bottom: 0.5in;
            }
        }

        * {
            box-sizing: border-box;
        }

        body {
            font-family: 'Times New Roman', Times, serif;
            font-size: 11pt;
            line-height: 1.6;
            color: #333;
            margin: 0;
            padding: 0;
        }

        .pdf-document {
            max-width: 100%;
        }

        /* Override existing styles for PDF optimization */
        .container {
            max-width: none !important;
            margin: 0 !important;
            padding: 0 !important;
        }

        h1 {
            color: #2563eb;
            font-size: 24pt;
            font-weight: bold;
            margin: 0 0 20px 0;
            line-height: 1.3;
            border-bottom: 2px solid #2563eb;
            padding-bottom: 15px;
        }

        h2 {
            color: #1f2937;
            font-size: 18pt;
            font-weight: bold;
            margin: 30px 0 15px 0;
            border-bottom: 1px solid #e5e7eb;
            padding-bottom: 5px;
        }

        h3 {
            color: #374151;
            font-size: 14pt;
            font-weight: bold;
            margin: 25px 0 12px 0;
        }

        h4 {
            color: #4b5563;
            font-size: 12pt;
            font-weight: bold;
            margin: 20px 0 10px 0;
        }

        p {
            margin: 12px 0;
            text-align: justify;
        }

        ul, ol {
            margin: 12px 0;
            padding-left: 30px;
        }

        li {
            margin: 6px 0;
        }

        strong, b {
            font-weight: bold;
            color: #1f2937;
        }

        em, i {
            font-style: italic;
        }

        /* Table styling */
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 1.5em 0;
            font-size: 10pt;
            border: 2px solid #333;
        }

        th, td {
            border: 1px solid #333;
            padding: 8px 12px;
            text-align: left;
            vertical-align: top;
        }

        th {
            background-color: #f0f0f0;
            font-weight: bold;
            border-bottom: 2px solid #333;
        }

        /* Code styling */
        code {
            background-color: #f6f8fa;
            padding: 2px 4px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 10pt;
        }

        pre {
            background-color: #f6f8fa;
            padding: 12px;
            border-radius: 6px;
            overflow: auto;
            font-family: 'Courier New', monospace;
            font-size: 9pt;
            line-height: 1.4;
        }

        /* Links */
        a {
            color: #2563eb;
            text-decoration: underline;
        }

        /* Blockquotes */
        blockquote {
            border-left: 4px solid #dfe2e5;
            margin: 1em 0;
            padding: 0 1em;
            color: #6a737d;
            font-style: italic;
        }

        /* Horizontal rules */
        hr {
            border: none;
            border-top: 1px solid #d1d5db;
            margin: 2em 0;
        }

        /* Ensure good page breaks */
        h1, h2, h3, h4 {
            page-break-after: avoid;
        }

        /* Watermark styling */
        .watermark {
            margin-top: 40px;
            padding: 20px 0;
            page-break-inside: avoid;
        }

        .watermark-divider {
            border: none;
            border-top: 2px solid #e5e7eb;
            margin: 20px 0 15px 0;
        }

        .watermark-content {
            text-align: center;
            font-size: 10pt;
            color: #6b7280;
            background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%);
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            padding: 12px 20px;
            margin: 0 auto;
            max-width: 500px;
        }

        .watermark-text {
            font-weight: normal;
            color: #4b5563;
        }

        .watermark-email {
            color: #6b7280;
            font-weight: normal;
        }

        .watermark-link {
            color: #2563eb;
            text-decoration: none;
            font-weight: 600;
            transition: color 0.2s ease;
        }

        .watermark-link:hover {
            color: #1d4ed8;
            text-decoration: underline;
        }

        .watermark-link:visited {
            color: #2563eb;
        }

        /* Print-friendly styles */
        @media print {
            body {
                font-size: 10pt;
            }

            h1 {
                font-size: 20pt;
            }

            h2 {
                font-size: 16pt;
            }

            .watermark-content {
                background: #f9fafb;
            }
        }
        """
