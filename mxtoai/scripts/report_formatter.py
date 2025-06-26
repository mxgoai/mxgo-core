import json
import re
from pathlib import Path
from typing import Any, Optional

import markdown2
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
            self.template_dir = Path(__file__).parent / "templates"
        else:
            self.template_dir = template_dir

        # Initialize Jinja environment and load themes
        self._init_template_env()
        self._load_themes()

        # Default signature
        self.signature_block = """

<hr style="margin: 2em 0; border: none; border-top: 1px solid #ddd;">

<p><strong>MXtoAI Assistant</strong></p>

<p><em>Feel free to reply to this email to continue our conversation.</em></p>
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
            themes_file = self.template_dir / "themes.json"
            if themes_file.exists():
                with themes_file.open() as f:
                    self.themes.update(json.load(f))
        except Exception as e:
            logger.error(f"Failed to load themes: {e}")

    def format_report(
        self, content: str, format_type: str = "markdown", *, include_signature: bool = True, theme: str = "default"
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

        # Apply markdown fixes for all formats
        content = self._fix_ai_markdown(content)

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

        except Exception:
            logger.exception("Error processing citations")
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
        # Handle tables first - convert markdown tables to plain text format
        text = self._convert_tables_to_plain_text(markdown)

        # Remove heading markers but preserve citations
        text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
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

    def _convert_tables_to_plain_text(self, markdown: str) -> str:
        """
        Convert markdown tables to readable plain text format.

        Args:
            markdown: Markdown content with tables

        Returns:
            Markdown with tables converted to plain text

        """
        lines = markdown.split("\n")
        result_lines = []
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Check if this looks like a table header
            if "|" in line and i + 1 < len(lines) and "|" in lines[i + 1] and "-" in lines[i + 1]:
                # Found a table, process it
                table_lines = [line]
                i += 1

                # Skip the separator line
                i += 1

                # Collect table rows
                while i < len(lines) and "|" in lines[i].strip():
                    table_lines.append(lines[i].strip())
                    i += 1

                # Convert table to plain text
                plain_table = self._format_table_as_plain_text(table_lines)
                result_lines.extend(plain_table)
                result_lines.append("")  # Add spacing after table

                continue
            result_lines.append(lines[i])
            i += 1

        return "\n".join(result_lines)

    def _format_table_as_plain_text(self, table_lines: list[str]) -> list[str]:
        """
        Format a markdown table as readable plain text.

        Args:
            table_lines: List of table lines (header + rows)

        Returns:
            List of formatted plain text lines

        """
        if not table_lines:
            return []

        # Parse table data
        rows = []
        for line in table_lines:
            # Remove leading/trailing pipes and split
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            rows.append(cells)

        if not rows:
            return []

        # Calculate column widths
        max_cols = max(len(row) for row in rows)
        col_widths = []

        for col in range(max_cols):
            max_width = 0
            for row in rows:
                if col < len(row):
                    max_width = max(max_width, len(row[col]))
            col_widths.append(max(max_width, 8))  # Minimum width of 8

        # Format as plain text
        result = []

        for row_idx, row in enumerate(rows):
            # Pad cells to column width with center alignment
            formatted_cells = []
            for col in range(max_cols):
                cell_content = row[col] if col < len(row) else ""
                formatted_cells.append(cell_content.center(col_widths[col]))

            # Join with spacing
            result.append("  ".join(formatted_cells).rstrip())

            # Add separator after header
            if row_idx == 0:
                separator_parts = ["-" * width for width in col_widths]
                result.append("  ".join(separator_parts))

        return result

    def _to_html(self, markdown_content: str, theme: str = "default") -> str:
        """
        Convert markdown to HTML using markdown2 for robust AI-generated content handling.

        Args:
            markdown_content: Markdown content (already processed by _fix_ai_markdown)
            theme: Theme name to use

        Returns:
            HTML version

        """
        # Convert markdown to HTML with markdown2 (robust for AI content)
        html_content = markdown2.markdown(
            markdown_content,
            extras=[
                "fenced-code-blocks",  # Support for ```code``` blocks
                "tables",  # Support for tables
                "strike",  # Support for ~~strikethrough~~
                "cuddled-lists",  # Better list handling (key for AI content!)
                "header-ids",  # Add IDs to headers
                "markdown-in-html",  # Allow markdown inside HTML
                "breaks",  # Handle line breaks better
            ],
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
        return self._basic_html_render(html_content)

    def _fix_ai_markdown(self, content: str) -> str:
        """
        Fix AI-generated markdown issues that markdown2 doesn't handle.
        This function performs several cleaning steps in a single pass over the lines.

        Args:
            content: Raw markdown content

        Returns:
            Fixed markdown content

        """
        lines = content.split("\n")
        result_lines = []

        for i, line in enumerate(lines):
            # --- FIX 1: Ensure headers are separated by a blank line ---
            if line.strip().startswith("#") and i > 0 and result_lines and result_lines[-1].strip() != "":
                # Insert blank line before header
                result_lines.append("")

            # --- FIX 1.5: Ensure consecutive bold text lines are separated ---
            # This handles cases like **Field**: value followed immediately by **Field2**: value2
            current_is_bold_field = line.strip().startswith("**") and "**:" in line
            if current_is_bold_field and i > 0 and result_lines:
                # Check if the previous line was also a bold field
                prev_line = result_lines[-1].strip()
                prev_is_bold_field = prev_line.startswith("**") and "**:" in prev_line
                if prev_is_bold_field:
                    # Insert blank line between consecutive bold fields
                    result_lines.append("")

            # --- FIX 2: Manually parse and fix bolded links in list items ---
            if line.strip().startswith(("*", "-")) and "**[" in line and "](" in line and ")**" in line:
                # This is a very specific pattern, so we can be confident in this replacement
                # Replace **[text](url)** with [**text**](url)
                modified_line = re.sub(r"\*\*\[(.*?)\]\((.*?)\)\*\*", r"[**\1**](\2)", line)
            else:
                modified_line = line

            # --- FIX 3: Convert letter-based lists to numbers ---
            # e.g., a. Item -> 1. Item
            match = re.match(r"^(\s*)([a-z])\.\s+(.*)$", modified_line)
            if match:
                indent, letter, text = match.groups()
                number = ord(letter) - ord("a") + 1
                modified_line = f"{indent}{number}. {text}"

            # --- FIX 4: Fix mixed list formatting ---
            # e.g., - 1. Item -> 1. Item
            modified_line = re.sub(r"^(\s*)[*-]\s+(\d+\.\s+.*)", r"\1\2", modified_line)

            # --- FIX 5: Fix missing spaces after list markers ---
            # Skip lines that start with bold markers like "**Summary:**"
            if not (
                modified_line.strip().startswith("**")
                and ("**:" in modified_line or modified_line.strip().endswith("**"))
            ):
                # Check for missing spaces after list markers
                match = re.match(r"^(\s*)(\d+\.|\*|-|\+)([^\s].*)", modified_line)
                if match:
                    indent, marker, rest_of_line = match.groups()
                    # It's a real list item, just missing a space
                    modified_line = f"{indent}{marker} {rest_of_line.lstrip()}"

            result_lines.append(modified_line)

        return "\n".join(result_lines)

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
            margin: 1.5em 0;
            font-size: 14px;
            border: 2px solid #333;
            background-color: #fff;
        }
        th, td {
            border: 1px solid #333;
            padding: 12px 16px;
            text-align: center;
            vertical-align: top;
        }
        th {
            background-color: #f0f0f0;
            font-weight: bold;
            color: #333;
            border-bottom: 2px solid #333;
        }
        tr:nth-child(even) td {
            background-color: #f9f9f9;
        }
        td:first-child {
            font-weight: 600;
            background-color: #f6f8fa;
            width: 30%;
        }
        table a {
            color: #0366d6;
            text-decoration: underline;
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
