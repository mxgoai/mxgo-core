import os
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any


class EmailProcessor:
    """
    Process email content and attachments.
    """

    def __init__(self, temp_dir: str = "email_attachments"):
        """
        Initialize the EmailProcessor.

        Args:
            temp_dir: Directory to store extracted attachments

        """
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)

    def process_email_file(self, email_file: str) -> dict[str, Any]:
        """
        Process an email file and extract its content and attachments.

        Args:
            email_file: Path to the email file (EML format)

        Returns:
            Dict containing email metadata, body, and attachment paths

        """
        with open(email_file, "rb") as fp:
            msg = BytesParser(policy=policy.default).parse(fp)

        # Extract basic metadata
        metadata = {
            "subject": msg.get("subject", ""),
            "from": msg.get("from", ""),
            "to": msg.get("to", ""),
            "date": msg.get("date", ""),
        }

        body = self._extract_body(msg)
        attachments = self._extract_attachments(msg, email_file)
        research_instructions = self._extract_research_instructions(body)

        return {
            "metadata": metadata,
            "body": body,
            "attachments": attachments,
            "research_instructions": research_instructions,
            "attachment_dir": os.path.join(self.temp_dir, Path(email_file).stem) if attachments else None,
        }

    def _extract_body(self, msg) -> str:
        """
        Extract the body content from the email message.

        Args:
            msg: Email message object

        Returns:
            Email body as plain text

        """
        body = ""

        # First, try to get the plain text body
        if msg.is_multipart():
            for part in msg.iter_parts():
                content_type = part.get_content_type()
                if content_type == "text/plain":
                    body = part.get_content()
                    break
                if content_type == "text/html" and not body:
                    # Use HTML if plain text isn't available
                    html_body = part.get_content()
                    # Simple HTML to text conversion (can be improved)
                    body = self._html_to_text(html_body)
        elif msg.get_content_type() == "text/plain":
            body = msg.get_content()
        elif msg.get_content_type() == "text/html":
            html_body = msg.get_content()
            body = self._html_to_text(html_body)

        return body

    def _html_to_text(self, html: str) -> str:
        """
        Convert HTML to plain text.

        Args:
            html: HTML content

        Returns:
            Plain text version of the HTML

        """
        # Simple implementation - can be improved with BeautifulSoup
        import re

        text = re.sub(r"<[^>]+>", " ", html)
        return re.sub(r"\s+", " ", text).strip()

    def _extract_attachments(self, msg, email_file: str) -> list[str]:
        """
        Extract attachments from the email message.

        Args:
            msg: Email message object
            email_file: Original email file path (used for naming)

        Returns:
            List of paths to extracted attachments

        """
        attachments = []
        attachment_dir = os.path.join(self.temp_dir, Path(email_file).stem)
        os.makedirs(attachment_dir, exist_ok=True)

        if msg.is_multipart():
            for _, part in enumerate(msg.iter_parts()):
                filename = part.get_filename()
                if filename:
                    # Clean the filename
                    filename = Path(filename).name
                    filepath = os.path.join(attachment_dir, filename)
                    with open(filepath, "wb") as fp:
                        fp.write(part.get_payload(decode=True))
                    attachments.append(filepath)

        return attachments

    def _extract_research_instructions(self, body: str) -> str:
        """
        Extract research instructions from the email body.
        This can be enhanced with NLP to better identify the actual request.

        Args:
            body: Email body text

        Returns:
            Extracted research instructions

        """
        # For now, we'll use a simple approach: the entire body is the instruction
        # In a more sophisticated implementation, this could use NLP to identify
        # specific instructions or questions
        return body
