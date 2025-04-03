import re
from typing import Any

from mxtoai._logging import get_logger

logger = get_logger(__name__)

class ReportFormatter:
    """Format research reports and emails for delivery."""

    def __init__(self):
        """Initialize the ReportFormatter."""
        self.html_style = """
            body {
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333333;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }
            p {
                margin-bottom: 1em;
            }
            h1, h2, h3, h4, h5, h6 {
                color: #2c3e50;
                margin-top: 1.5em;
                margin-bottom: 0.5em;
            }
            /* Base list styles */
            ul, ol {
                margin: 0.5em 0 1em 0;
                padding-left: 2em;
                list-style-position: outside;
            }
            /* Specific list styles */
            ul {
                list-style-type: disc;
            }
            ol {
                list-style-type: decimal;
            }
            /* Nested list styles */
            ul ul, ol ul {
                list-style-type: circle;
                margin: 0.3em 0 0.3em 1em;
            }
            ul ul ul, ol ul ul {
                list-style-type: square;
            }
            ol ol, ul ol {
                list-style-type: lower-alpha;
                margin: 0.3em 0 0.3em 1em;
            }
            ol ol ol, ul ol ol {
                list-style-type: lower-roman;
            }
            /* List item spacing and formatting */
            li {
                margin: 0.5em 0;
                padding-left: 0.3em;
                line-height: 1.4;
                display: list-item;
            }
            /* Handle mixed formatting in list items */
            li em, li strong {
                display: inline;
                vertical-align: baseline;
            }
            li > em, li > strong {
                display: inline;
                vertical-align: baseline;
            }
            /* Ensure proper spacing for formatted text in lists */
            li p {
                margin: 0;
                display: inline;
            }
            /* Handle multi-line list items */
            li > ul,
            li > ol {
                margin-top: 0.3em;
                margin-bottom: 0.3em;
                margin-left: 1em;
            }
            /* Nested list indentation */
            ol > li, ul > li {
                margin-left: 0;
            }
            li > ul > li,
            li > ol > li {
                margin-left: 0;
            }
            /* Fix for mixed content in list items */
            li > *:not(ul):not(ol) {
                display: inline-block;
                margin: 0;
                vertical-align: top;
            }
            /* Ensure proper alignment of text with bullets/numbers */
            li::marker {
                unicode-bidi: isolate;
                font-variant-numeric: tabular-nums;
                text-align: end;
                text-align-last: end;
            }
            a {
                color: #3498db;
                text-decoration: none;
            }
            a:hover {
                text-decoration: underline;
            }
            hr {
                border: none;
                border-top: 1px solid #e0e0e0;
                margin: 20px 0;
            }
            .signature {
                color: #666666;
                font-style: italic;
                border-top: 1px solid #e0e0e0;
                padding-top: 15px;
                margin-top: 25px;
            }
            code {
                background-color: #f5f5f5;
                padding: 2px 4px;
                border-radius: 3px;
                font-family: monospace;
            }
            pre {
                background-color: #f5f5f5;
                padding: 15px;
                border-radius: 5px;
                overflow-x: auto;
                margin: 1em 0;
            }
            strong {
                color: #2c3e50;
                font-weight: 600;
            }
            em {
                color: #34495e;
                font-style: italic;
            }
            /* Ensure em and strong work together */
            em strong, strong em {
                color: #2c3e50;
                font-weight: 600;
                font-style: italic;
            }
            blockquote {
                border-left: 4px solid #e0e0e0;
                margin: 1em 0;
                padding-left: 1em;
                color: #666666;
            }
            /* Citation and reference styles */
            .citation {
                font-size: 0.8em;
                vertical-align: super;
                color: #666666;
            }
            .citation a {
                color: #666666;
                text-decoration: none;
            }
            .citation a:hover {
                text-decoration: underline;
            }
            .references {
                margin-top: 2em;
                padding-top: 1em;
                border-top: 1px solid #e0e0e0;
            }
            .reference {
                margin: 0.5em 0;
                padding: 0.5em;
                background-color: #f8f9fa;
                border-left: 3px solid #e0e0e0;
                font-size: 0.9em;
            }
            .reference-number {
                color: #666666;
                font-weight: bold;
                margin-right: 0.5em;
            }
            .toc {
                background-color: #f8f9fa;
                padding: 1em;
                margin: 1em 0;
                border-radius: 5px;
            }
            .toc ul {
                list-style-type: none;
                padding-left: 1em;
            }
            .toc li {
                margin: 0.5em 0;
            }
        """

        self.signature_block = """

---

**MXtoAI Assistant**

_Feel free to reply to this email to continue our conversation._
"""

    def format_report(self, content: str, format_type: str = "markdown", include_signature: bool = True) -> str:
        """
        Format the research report in the specified format.

        Args:
            content: Report content
            format_type: Output format (text, html, markdown)
            include_signature: Whether to include the signature block

        Returns:
            Formatted report

        """
        # Remove any existing signatures
        content = self._remove_existing_signatures(content)

        # Process citations and references before converting format
        # DISABLED: _process_citations was causing issues with already formatted markdown.
        # The DeepResearchTool now handles citation/reference formatting directly.
        # if format_type == "html":
        #     content = self._process_citations(content)

        # Add signature if requested
        if include_signature:
            content = content.rstrip() + self.signature_block

        if format_type == "text":
            return self._to_plain_text(content)
        if format_type == "html":
            return self._to_html(content)
        # markdown (default)
        return content

    def _process_citations(self, content: str) -> str:
        """Process citations and references in the content."""
        try:
            # Find all references sections
            reference_sections = list(re.finditer(r"(?:###\s*References|\n## References)(.*?)(?=###|\Z|\n## )", content, re.DOTALL))

            if not reference_sections:
                return content

            # Get the last references section (usually the most complete one)
            references_match = reference_sections[-1]
            references_section = references_match.group(1).strip()

            # Create a mapping of reference numbers to their full citations
            ref_map = {}
            for ref in re.finditer(r"(?:^|\n)(?:\[)?(\d+)(?:\])?\.\s*(.*?)(?=(?:\n(?:\[)?\d+(?:\])?\.|$))", references_section, re.DOTALL):
                ref_num = ref.group(1)
                ref_text = ref.group(2).strip()
                ref_map[ref_num] = ref_text

            # Replace citations in the main text with HTML formatted versions
            def replace_citation(match):
                num = match.group(1)
                if num in ref_map:
                    return f'<sup class="citation">[<a href="#ref-{num}" title="{ref_map[num]}">{num}</a>]</sup>'
                return match.group(0)

            # Replace citations in the content
            content = re.sub(r"\[(\d+)\]", replace_citation, content)

            # Format the references section
            formatted_refs = ['<div class="references">', "<h2>References</h2>"]
            for num, text in sorted(ref_map.items(), key=lambda x: int(x[0])):
                formatted_refs.append(
                    f'<div class="reference" id="ref-{num}">'
                    f'<span class="reference-number">[{num}]</span> {text}'
                    '</div>'
                )
            formatted_refs.append("</div>")

            # Remove all existing references sections
            for section in reversed(reference_sections):
                content = content[:section.start()] + content[section.end():]

            # Add the formatted references section at the end
            return content.strip() + "\n\n" + "\n".join(formatted_refs)


        except Exception as e:
            # Log error but don't break formatting
            logger.exception(f"Error processing citations: {e!s}")
            return content

    def _remove_existing_signatures(self, content: str) -> str:
        """Remove any existing signature blocks from the content."""
        signature_patterns = [
            r"\n\s*Warm regards,?\s*\n\s*MXtoAI Assistant\s*\n",
            r"\n\s*Best regards,?\s*\n\s*MXtoAI Assistant\s*\n",
            r"\n\s*Best,\s*\n\s*MXtoAI Assistant\s*\n",
            r"\n\s*Regards,?\s*\n\s*MXtoAI Assistant\s*\n",
            r"\n\s*Sincerely,?\s*\n\s*MXtoAI Assistant\s*\n"
        ]
        result = content
        for pattern in signature_patterns:
            result = re.sub(pattern, "", result, flags=re.IGNORECASE)
        return result

    def _to_plain_text(self, markdown: str) -> str:
        """
        Convert markdown to plain text while preserving citations.

        Args:
            markdown: Markdown content

        Returns:
            Plain text version

        """
        # Remove heading markers but preserve citations
        text = re.sub(r"^#+\s+", "", markdown, flags=re.MULTILINE)
        # Remove bold markers
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"__(.*?)__", r"\1", text)
        # Remove italic markers (both * and _)
        text = re.sub(r"(?<!\\)\*((?:[^*]|\\[*])+?)(?<!\\)\*", r"\1", text)
        text = re.sub(r"(?<!\\)_((?:[^_]|\\_)+?)(?<!\\)_", r"\1", text)
        # Convert links: [Title](URL) -> Title (URL), but don't touch existing [N] citations
        text = re.sub(r"\[([^\]\d]+?)\]\((.*?)\)", r"\1 (\2)", text)
        # Remove code blocks
        text = re.sub(r"```.*?\n(.*?)```", r"\1", text, flags=re.DOTALL)
        # Remove horizontal rules
        text = re.sub(r"^---+", "-" * 40, text, flags=re.MULTILINE)
        # Handle lists (basic conversion)
        text = re.sub(r"^\s*\*\s+", "- ", text, flags=re.MULTILINE)
        text = re.sub(r"^\s*\d+\.\s+", "  ", text, flags=re.MULTILINE)
        # Clean up extra newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _to_html(self, markdown_content: str) -> str:
        """
        Convert markdown to HTML while preserving citations and references.

        Args:
            markdown_content: Markdown content

        Returns:
            HTML version

        """
        try:
            import markdown as md_converter
            from markdown.extensions.attr_list import AttrListExtension
            from markdown.extensions.fenced_code import FencedCodeExtension
            from markdown.extensions.nl2br import Nl2BrExtension
            from markdown.extensions.sane_lists import SaneListExtension
            from markdown.extensions.tables import TableExtension
            from markdown.extensions.toc import TocExtension

            # Configure extensions with specific settings
            extensions = [
                TableExtension(),  # Support for tables
                FencedCodeExtension(),  # Support for fenced code blocks
                SaneListExtension(),  # Better list handling
                Nl2BrExtension(),  # Convert newlines to line breaks
                TocExtension(permalink=False),  # Table of contents support without permalinks
                AttrListExtension(),  # Support for attributes
            ]

            # Convert markdown to HTML with configured extensions
            html = md_converter.markdown(
                markdown_content,
                extensions=extensions,
                extension_configs={
                    # Explicitly disable footnotes if it's a default or separate extension
                    # 'markdown.extensions.footnotes': {'PLACE_MARKER': '!!!!FOOTNOTES!!!!'}
                },
                output_format="html5" # Use html5 for better compatibility
            )

            return f"""
                <html>
                <head>
                <style>
                {self.html_style}
                /* Enhanced table styles */
                table {{
                    border-collapse: collapse;
                    width: 100%;
                    margin: 1.5em 0;
                    font-size: 0.95em;
                }}
                th, td {{
                    border: 1px solid #ddd;
                    padding: 12px;
                    text-align: left;
                    vertical-align: top;
                }}
                th {{
                    background-color: #f5f5f5;
                    font-weight: 600;
                    color: #2c3e50;
                }}
                tr:nth-child(even) {{
                    background-color: #f9f9f9;
                }}
                tr:hover {{
                    background-color: #f5f5f5;
                }}
                /* List within table cells */
                td ul, td ol {{
                    margin: 0;
                    padding-left: 1.5em;
                }}
                td li {{
                    margin: 0.2em 0;
                }}
                /* Enhanced list styling */
                ol {{
                    counter-reset: item;
                    list-style-type: decimal;
                }}
                ul {{
                    list-style-type: disc;
                }}
                ol ol {{
                    list-style-type: lower-alpha;
                }}
                ul ul {{
                    list-style-type: circle;
                }}
                ol ul {{
                    list-style-type: circle;
                }}
                ul ol {{
                    list-style-type: lower-alpha;
                }}
                /* Ensure proper list indentation */
                ol, ul {{
                    padding-left: 2em;
                    margin-bottom: 1em;
                }}
                ol ol, ul ul, ol ul, ul ol {{
                    margin-left: 1em;
                    margin-bottom: 0;
                }}
                li {{
                    margin-bottom: 0.5em;
                }}
                li li {{
                    margin-bottom: 0.25em;
                }}
                /* Fix for nested list spacing */
                li > ul,
                li > ol {{
                    margin-top: 0.5em;
                    margin-bottom: 0.5em;
                }}
                </style>
                </head>
                <body>
                {html}
                </body>
                </html>
            """
        except ImportError:
            logger.error("Markdown package not available - this should never happen as it's a required dependency")
            raise  # We should always have markdown package available

    def add_email_header_footer(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        """
        Add email header and footer to the report.

        Args:
            content: Report content
            metadata: Email metadata

        Returns:
            Report with header and footer

        """
        if not metadata:
            metadata = {}

        subject = metadata.get("subject", "Research Report")
        sender = metadata.get("from", "")
        date = metadata.get("date", "")

        header = f"Subject: {subject}\n"
        if sender:
            header += f"From: {sender}\n"
        if date:
            header += f"Date: {date}\n"
        header += "\n" + "-" * 40 + "\n\n"

        footer = "\n\n" + "-" * 40 + "\n"
        footer += "This report was generated by the MXtoAI Deep Research Agent.\n"
        footer += "If you have any questions, please reply to this email.\n"

        return header + content + footer
