import json
import os
import re
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from mxtoai._logging import get_logger

logger = get_logger(__name__)


class ReportFormatter:
    """
    Format research reports and emails for delivery.
    """

    def __init__(self, template_dir: Optional[str] = None):
        """
        Initialize the ReportFormatter with configurable templates.

        Args:
            template_dir: Directory containing template files (defaults to package templates)

        """
        # Set up template directory
        if template_dir is None:
            self.template_dir = os.path.join(os.path.dirname(__file__), "templates")
        else:
            self.template_dir = template_dir

        # Initialize Jinja environment and load themes
        self._init_template_env()
        self._load_themes()

        # Default signature
        self.signature_block = """

---

**MXtoAI Assistant**

_Feel free to reply to this email to continue our conversation._
"""

    def _init_template_env(self):
        """
        Initialize the Jinja2 template environment.
        """
        try:
            self.template_env = Environment(
                loader=FileSystemLoader(self.template_dir),
                autoescape=select_autoescape(["html", "xml"]),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        except Exception as e:
            logger.error(f"Failed to initialize template environment: {e}")
            self.template_env = None

    def _load_themes(self):
        """
        Load available CSS themes from the themes directory.

        """
        self.themes = {"default": {}}  # Always have a default theme

        try:
            themes_file = os.path.join(self.template_dir, "themes.json")
            if os.path.exists(themes_file):
                with open(themes_file) as f:
                    self.themes.update(json.load(f))
        except Exception as e:
            logger.error(f"Failed to load themes: {e}")

    def format_report(
        self, content: str, format_type: str = "markdown", include_signature: bool = True, theme: str = "default"
    ) -> str:
        """
        Format the research report in the specified format.

        Args:
            content: Report content
            format_type: Output format (text, html, markdown)
            include_signature: Whether to include the signature block
            theme: Theme name to use for HTML formatting

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
            return self._to_html(content, theme)
        # markdown (default)
        return content

    def _process_citations(self, content: str) -> str:
        """
        Process citations and references in the content.

        Args:
            content: Report content
        Returns:
            Processed content with citations and references formatted

        """
        try:
            # Find all references sections
            reference_sections = list(
                re.finditer(r"(?:###\s*References|\n## References)(.*?)(?=###|\Z|\n## )", content, re.DOTALL)
            )

            if not reference_sections:
                return content

            # Get the last references section (usually the most complete one)
            references_match = reference_sections[-1]
            references_section = references_match.group(1).strip()

            # Create a mapping of reference numbers to their full citations
            ref_map = {}
            for ref in re.finditer(
                r"(?:^|\n)(?:\[)?(\d+)(?:\])?\.\s*(.*?)(?=(?:\n(?:\[)?\d+(?:\])?\.|$))", references_section, re.DOTALL
            ):
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
                    f'<div class="reference" id="ref-{num}"><span class="reference-number">[{num}]</span> {text}</div>'
                )
            formatted_refs.append("</div>")

            # Remove all existing references sections
            for section in reversed(reference_sections):
                content = content[: section.start()] + content[section.end() :]

            # Add the formatted references section at the end
            return content.strip() + "\n\n" + "\n".join(formatted_refs)

        except Exception as e:
            logger.exception(f"Error processing citations: {e!s}")
            return content

    def _remove_existing_signatures(self, content: str) -> str:
        """
        Remove any existing signature blocks from the content.

        Args:
            content: Report content
        Returns:
            Content with existing signatures removed

        """
        signature_patterns = [
            r"\n\s*Warm regards,?\s*\n\s*MXtoAI Assistant\s*\n",
            r"\n\s*Best regards,?\s*\n\s*MXtoAI Assistant\s*\n",
            r"\n\s*Best,\s*\n\s*MXtoAI Assistant\s*\n",
            r"\n\s*Regards,?\s*\n\s*MXtoAI Assistant\s*\n",
            r"\n\s*Sincerely,?\s*\n\s*MXtoAI Assistant\s*\n",
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

    def _to_html(self, markdown_content: str, theme: str = "default") -> str:
        """
        Convert markdown to HTML using templates and themes.

        Args:
            markdown_content: Markdown content
            theme: Theme name to use

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

            # Pre-process to ensure lists following non-empty lines have a preceding blank line
            markdown_content = re.sub(r'([^\n])\n(\s*(?:[-*+]|\d+\.)[ \t])', r'\1\n\n\2', markdown_content)

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
            html_content = md_converter.markdown(
                markdown_content,
                extensions=extensions,
                extension_configs={
                    # Explicitly disable footnotes if it's a default or separate extension
                    # 'markdown.extensions.footnotes': {'PLACE_MARKER': '!!!!FOOTNOTES!!!!'}
                },
                output_format="html5",  # Use html5 for better compatibility
            )

            if self.template_env:
                try:
                    theme_settings = self.themes.get(theme, self.themes["default"])
                    template = self.template_env.get_template("email_template.html")

                    return template.render(content=html_content, theme=theme_settings)
                except Exception as e:
                    logger.error(f"Template rendering failed: {e}. Falling back to basic rendering.")

            # fallback
            logger.info("Template environment not available. Using basic HTML rendering.")
            return self._basic_html_render(html_content, theme)

        except ImportError:
            logger.error("Markdown package not available - this should never happen as it's a required dependency")
            raise  # We should always have markdown package available

    def _basic_html_render(self, html_content: str) -> str:
        """
        Fallback HTML rendering when templates aren't available.

        Args:
            html_content: HTML content to render

        Returns:
            Basic HTML structure with inline CSS

        """
        # Get minimal inline CSS
        css = self._get_minimal_css()

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>{css}</style>
        </head>
        <body>
            <div class="container">
                {html_content}
            </div>
        </body>
        </html>
        """

    def _get_minimal_css(self) -> str:
        """
        Get minimal CSS for fallback rendering.
        """
        return """
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }
        .container {
            width: 100%;
        }
        h1, h2, h3, h4, h5, h6 {
            margin-top: 1.5em;
            margin-bottom: 0.5em;
            color: #222;
        }
        /* Improved list styling for consistent indentation */
        ul, ol {
            padding-left: 2em;
            margin: 0.8em 0 1em 0;
            list-style-position: outside;
        }
        /* Nested lists - consistent indentation */
        ul ul, ol ul,
        ul ol, ol ol {
            padding-left: 1.5em;
            margin: 0.5em 0;
        }
        li {
            margin: 0.5em 0;
            line-height: 1.5;
            display: list-item;
        }
        /* Handle paragraphs in lists */
        li p {
            margin: 0.5em 0;
        }
        a {
            color: #0366d6;
            text-decoration: none;
        }
        a:hover {
            text-decoration: underline;
        }
        code {
            background-color: #f6f8fa;
            padding: 0.2em 0.4em;
            border-radius: 3px;
            font-family: SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace;
        }
        pre {
            background-color: #f6f8fa;
            padding: 16px;
            border-radius: 6px;
            overflow: auto;
            font-family: SFMono-Regular, Consolas, Liberation Mono, Menlo, monospace;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin: 1em 0;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
        }
        th {
            background-color: #f6f8fa;
        }
        tr:nth-child(even) {
            background-color: #f9f9f9;
        }
        blockquote {
            border-left: 4px solid #dfe2e5;
            margin: 0;
            padding: 0 1em;
            color: #6a737d;
        }
        """

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
