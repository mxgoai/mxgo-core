import re
from typing import Dict, Any, Optional


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
            ul, ol {
                margin-bottom: 1em;
                padding-left: 2em;
            }
            li {
                margin-bottom: 0.5em;
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
            }
            em {
                color: #34495e;
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
        if format_type == "html":
            content = self._process_citations(content)
        
        # Add signature if requested
        if include_signature:
            content = content.rstrip() + self.signature_block
        
        if format_type == "text":
            return self._to_plain_text(content)
        elif format_type == "html":
            return self._to_html(content)
        else:  # markdown (default)
            return content
    
    def _process_citations(self, content: str) -> str:
        """Process citations and references in the content."""
        try:
            # Find all references sections
            reference_sections = list(re.finditer(r'(?:###\s*References|\n## References)(.*?)(?=###|\Z|\n## )', content, re.DOTALL))
            
            if not reference_sections:
                return content
                
            # Get the last references section (usually the most complete one)
            references_match = reference_sections[-1]
            references_section = references_match.group(1).strip()
            
            # Create a mapping of reference numbers to their full citations
            ref_map = {}
            for ref in re.finditer(r'(?:^|\n)(?:\[)?(\d+)(?:\])?\.\s*(.*?)(?=(?:\n(?:\[)?\d+(?:\])?\.|$))', references_section, re.DOTALL):
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
            content = re.sub(r'\[(\d+)\]', replace_citation, content)
            
            # Format the references section
            formatted_refs = ['<div class="references">', '<h2>References</h2>']
            for num, text in sorted(ref_map.items(), key=lambda x: int(x[0])):
                formatted_refs.append(
                    f'<div class="reference" id="ref-{num}">'
                    f'<span class="reference-number">[{num}]</span> {text}'
                    '</div>'
                )
            formatted_refs.append('</div>')
            
            # Remove all existing references sections
            for section in reversed(reference_sections):
                content = content[:section.start()] + content[section.end():]
            
            # Add the formatted references section at the end
            content = content.strip() + '\n\n' + '\n'.join(formatted_refs)
            
            return content
            
        except Exception as e:
            # Log error but don't break formatting
            import logging
            logging.error(f"Error processing citations: {str(e)}")
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
        text = re.sub(r"#+\s+(?!References)", "", markdown)  # Don't remove "References" header
        # Remove bold markers
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"__(.*?)__", r"\1", text)
        # Remove italic markers (both * and _)
        text = re.sub(r"(?<!\\)\*((?:[^*]|\\[*])+?)(?<!\\)\*", r"\1", text)
        text = re.sub(r"(?<!\\)_((?:[^_]|\\_)+?)(?<!\\)_", r"\1", text)
        # Remove link formatting but preserve URLs in references
        text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", text)
        # Remove code blocks
        text = re.sub(r"```.*?\n(.*?)```", r"\1", text, flags=re.DOTALL)
        # Remove horizontal rules
        text = re.sub(r"---+", "-" * 40, text)
        return text
    
    def _to_html(self, markdown_content: str) -> str:
        """
        Convert markdown to HTML while preserving citations and references.
        
        Args:
            markdown_content: Markdown content
            
        Returns:
            HTML version
        """
        def convert_lists(html_content):
            """Convert markdown lists to HTML with proper nesting."""
            lines = html_content.split('\n')
            result = []
            list_stack = []  # Stack to track nested lists
            
            for line in lines:
                # Count leading spaces to determine indentation level
                indent = len(re.match(r'^\s*', line).group())
                line = line.strip()
                
                # Check if line is a list item
                ordered_match = re.match(r'^\d+\.\s+(.+)$', line)
                unordered_match = re.match(r'^[-*]\s+(.+)$', line)
                
                if ordered_match or unordered_match:
                    # Get the list item content
                    content = ordered_match.group(1) if ordered_match else unordered_match.group(1)
                    is_ordered = bool(ordered_match)
                    
                    # Close lists that are too deep
                    while list_stack and list_stack[-1]['indent'] > indent:
                        list_type = 'ol' if list_stack[-1]['ordered'] else 'ul'
                        result.append(' ' * list_stack[-1]['indent'] + f'</{list_type}>')
                        list_stack.pop()
                    
                    # Start new list if needed
                    if not list_stack or indent > list_stack[-1]['indent']:
                        list_type = 'ol' if is_ordered else 'ul'
                        result.append(' ' * indent + f'<{list_type}>')
                        list_stack.append({'indent': indent, 'ordered': is_ordered})
                    
                    # Add list item
                    result.append(' ' * indent + f'<li>{content}</li>')
                else:
                    # Close all open lists when encountering non-list content
                    while list_stack:
                        list_type = 'ol' if list_stack[-1]['ordered'] else 'ul'
                        result.append(' ' * list_stack[-1]['indent'] + f'</{list_type}>')
                        list_stack.pop()
                    result.append(line)
            
            # Close any remaining open lists
            while list_stack:
                list_type = 'ol' if list_stack[-1]['ordered'] else 'ul'
                result.append(' ' * list_stack[-1]['indent'] + f'</{list_type}>')
                list_stack.pop()
            
            return '\n'.join(result)

        try:
            import markdown as md_converter
            # Convert markdown to HTML
            html_content = md_converter.markdown(
                markdown_content,
                extensions=['tables', 'fenced_code', 'nl2br', 'toc']
            )
            
            # Apply list conversion
            html = convert_lists(html_content)
            
            return f"""
                <html>
                <head>
                <style>
                {self.html_style}
                </style>
                </head>
                <body>
                {html}
                </body>
                </html>
            """
        except ImportError:
            # Fallback if markdown package is not available
            html = markdown_content
            
            # Convert headings (improved to handle multiple lines)
            for i in range(6, 0, -1):
                pattern = r"^#{" + str(i) + r"}\s+(.+)$"
                repl = f"<h{i}>\g<1></h{i}>"
                html = re.sub(pattern, repl, html, flags=re.MULTILINE)
            
            # Convert lists using the same improved handler
            html = convert_lists(html)
            
            # Convert bold
            html = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", html)
            # Convert italic (both * and _ styles)
            html = re.sub(r"(?<!\\)_([^_]+?)(?<!\\)_", r"<em>\1</em>", html)
            html = re.sub(r"(?<!\\)\*([^\*]+?)(?<!\\)\*", r"<em>\1</em>", html)
            # Convert links
            html = re.sub(r"\[(.*?)\]\((.*?)\)", r'<a href="\2">\1</a>', html)
            # Convert code blocks
            html = re.sub(r"```.*?\n(.*?)```", r"<pre><code>\1</code></pre>", html, flags=re.DOTALL)
            # Convert horizontal rules
            html = re.sub(r"^---+$", r"<hr/>", html, flags=re.MULTILINE)
            # Convert paragraphs (improved)
            html = re.sub(r"\n\n+", "\n</p>\n<p>", html)
            html = f"<p>{html}</p>"
            
            return f"""
                <html>
                <head>
                <style>
                {self.html_style}
                </style>
                </head>
                <body>
                {html}
                </body>
                </html>
            """
    
    def add_email_header_footer(self, content: str, metadata: Dict[str, Any] = None) -> str:
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