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
        
        # Add signature if requested
        if include_signature:
            content = content.rstrip() + self.signature_block
        
        if format_type == "text":
            return self._to_plain_text(content)
        elif format_type == "html":
            return self._to_html(content)
        else:  # markdown (default)
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
        Convert markdown to plain text.
        
        Args:
            markdown: Markdown content
            
        Returns:
            Plain text version
        """
        # Remove heading markers
        text = re.sub(r"#+\s+", "", markdown)
        # Remove bold markers
        text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
        text = re.sub(r"__(.*?)__", r"\1", text)
        # Remove italic markers (both * and _)
        text = re.sub(r"(?<!\\)\*((?:[^*]|\\[*])+?)(?<!\\)\*", r"\1", text)
        text = re.sub(r"(?<!\\)_((?:[^_]|\\_)+?)(?<!\\)_", r"\1", text)
        # Remove link formatting
        text = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1 (\2)", text)
        # Remove code blocks
        text = re.sub(r"```.*?\n(.*?)```", r"\1", text, flags=re.DOTALL)
        # Remove horizontal rules
        text = re.sub(r"---+", "-" * 40, text)
        return text
    
    def _to_html(self, markdown: str) -> str:
        """
        Convert markdown to HTML.
        
        Args:
            markdown: Markdown content
            
        Returns:
            HTML version
        """
        try:
            import markdown
            html_content = markdown.markdown(markdown, extensions=['tables', 'fenced_code', 'nl2br'])
            return f"""
                <html>
                <head>
                <style>
                {self.html_style}
                </style>
                </head>
                <body>
                {html_content}
                </body>
                </html>
            """
        except ImportError:
            # Fallback if markdown package is not available
            html = markdown
            
            # Convert headings (improved to handle multiple lines)
            for i in range(6, 0, -1):
                pattern = r"^#{" + str(i) + r"}\s+(.+)$"
                repl = f"<h{i}>\g<1></h{i}>"
                html = re.sub(pattern, repl, html, flags=re.MULTILINE)
            
            # Convert lists
            html = re.sub(r"^\d+\.\s+(.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
            html = re.sub(r"^-\s+(.+)$", r"<li>\1</li>", html, flags=re.MULTILINE)
            html = re.sub(r"(<li>.*?</li>\n)+", r"<ul>\g<0></ul>", html, flags=re.DOTALL)
            
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