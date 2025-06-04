import tempfile
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import re

from smolagents import Tool
from mxtoai._logging import get_logger
from mxtoai.scripts.report_formatter import ReportFormatter

logger = get_logger("pdf_export_tool")

class PDFExportTool(Tool):
    """Tool for exporting email content and research findings to PDF format."""

    name = "pdf_export"
    description = "Export email content, research findings, and attachment summaries to a professionally formatted PDF document"

    inputs = {
        "content": {
            "type": "string",
            "description": "The main content to export (email body, research findings, etc.)"
        },
        "title": {
            "type": "string",
            "description": "Title for the PDF document",
            "nullable": True
        },
        "research_findings": {
            "type": "string",
            "description": "Additional research findings to include",
            "nullable": True
        },
        "attachments_summary": {
            "type": "string",
            "description": "Summary of processed attachments",
            "nullable": True
        },
        "include_attachments": {
            "type": "boolean",
            "description": "Whether to include attachment summaries in the PDF",
            "default": False,
            "nullable": True
        }
    }
    output_type = "object"

    def __init__(self):
        super().__init__()
        self.temp_dir = Path(tempfile.mkdtemp())
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.report_formatter = ReportFormatter()

    def forward(
        self,
        content: str,
        title: Optional[str] = None,
        research_findings: Optional[str] = None,
        attachments_summary: Optional[str] = None,
        include_attachments: bool = False
    ) -> Dict[str, Any]:
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
            # Import WeasyPrint here to avoid import errors if not installed
            from weasyprint import HTML, CSS
        except ImportError as e:
            logger.error(f"WeasyPrint not available: {e}")
            return {
                "error": "PDF generation library not available. Please install WeasyPrint.",
                "details": str(e)
            }

        try:
            # Clean and prepare content
            cleaned_content = self._clean_content(content)
            doc_title = title or self._extract_title(cleaned_content)

            # Build complete markdown document
            markdown_document = self._build_markdown_document(
                content=cleaned_content,
                title=doc_title,
                research_findings=research_findings,
                attachments_summary=attachments_summary if include_attachments else None
            )

            # Convert to HTML using existing ReportFormatter
            html_content = self.report_formatter._to_html(markdown_document, theme="default")

            # Enhance HTML for PDF with custom CSS
            pdf_html = self._enhance_html_for_pdf(html_content, doc_title)

            # Generate PDF
            filename = self._sanitize_filename(doc_title) + ".pdf"
            pdf_path = self.temp_dir / filename

            HTML(string=pdf_html).write_pdf(
                pdf_path,
                stylesheets=[CSS(string=self._get_pdf_styles())]
            )

            file_size = pdf_path.stat().st_size

            return {
                "success": True,
                "filename": filename,
                "file_path": str(pdf_path),
                "file_size": file_size,
                "mimetype": "application/pdf",
                "title": doc_title,
                "pages_estimated": max(1, len(cleaned_content) // 2000)  # Rough estimate
            }

        except Exception as e:
            logger.error(f"PDF export failed: {e}")
            return {
                "error": f"PDF export failed: {str(e)}",
                "details": "Please check the content format and try again"
            }

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
            r'^From:.*$',
            r'^To:.*$',
            r'^Subject:.*$',
            r'^Date:.*$',
            r'^CC:.*$',
            r'^BCC:.*$',
            r'^Reply-To:.*$',
            r'^Message-ID:.*$',
            r'^In-Reply-To:.*$',
            r'^References:.*$',
            r'^Received:.*$',
            r'^Return-Path:.*$'
        ]

        lines = content.split('\n')
        cleaned_lines = []

        for line in lines:
            # Skip lines that match email header patterns
            is_header = any(re.match(pattern, line.strip(), re.IGNORECASE) for pattern in email_header_patterns)
            if not is_header:
                cleaned_lines.append(line)

        cleaned_content = '\n'.join(cleaned_lines).strip()

        # Remove excessive whitespace but preserve paragraph breaks
        cleaned_content = re.sub(r'\n\s*\n\s*\n+', '\n\n', cleaned_content)
        cleaned_content = re.sub(r'[ \t]+', ' ', cleaned_content)

        return cleaned_content

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
        lines = content.split('\n')
        for line in lines[:10]:  # Check first 10 lines
            line = line.strip()
            if line.startswith('# '):
                return line[2:].strip()[:60]  # Remove # and limit length
            elif line.startswith('## '):
                return line[3:].strip()[:60]  # Remove ## and limit length

        # Look for lines that could be titles (short, meaningful lines)
        for line in lines[:5]:  # Check first 5 lines
            line = line.strip()
            if line and len(line) < 100 and len(line) > 5:
                # Check if it looks like a title (no common body text indicators)
                if not any(indicator in line.lower() for indicator in
                          ['the', 'this', 'that', 'with', 'from', 'email', 'message']):
                    return line[:60]

        # Fallback: use first meaningful sentence
        sentences = re.split(r'[.!?]+', content)
        for sentence in sentences[:3]:
            sentence = sentence.strip()
            if 10 < len(sentence) < 80:
                return sentence[:60]

        return f"Document - {datetime.now().strftime('%B %d, %Y')}"

    def _sanitize_filename(self, filename: str) -> str:
        """
        Sanitize filename for file system compatibility.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        # Remove or replace invalid characters
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        filename = re.sub(r'\s+', '_', filename)
        filename = filename[:50]  # Limit length
        return filename if filename else "document"

    def _build_markdown_document(
        self,
        content: str,
        title: str,
        research_findings: Optional[str] = None,
        attachments_summary: Optional[str] = None
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
        markdown_parts.append(f"*Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}*\n")

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

        # Add watermark as markdown comment (will be styled in CSS)
        markdown_parts.append("\n\n---\n*Generated via pdf@mxtoai.com*")

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
        if '<body>' in html_content:
            # Extract content between body tags
            import re
            body_match = re.search(r'<body[^>]*>(.*?)</body>', html_content, re.DOTALL)
            if body_match:
                body_content = body_match.group(1)
            else:
                body_content = html_content
        else:
            body_content = html_content

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
                {body_content}
            </div>
        </body>
        </html>
        """

    def _html_escape(self, text: str) -> str:
        """Escape HTML special characters."""
        if not text:
            return ""
        return (text.replace('&', '&amp;')
                   .replace('<', '&lt;')
                   .replace('>', '&gt;')
                   .replace('"', '&quot;')
                   .replace("'", '&#x27;'))

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
        }
        """