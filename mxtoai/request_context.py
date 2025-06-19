"""
Request Context for Email Agent Processing.

Centralizes email request data, citations management, and processing context
to provide clean architecture and request isolation.
"""

from datetime import datetime, timezone
from typing import Any

from mxtoai.schemas import CitationCollection, CitationSource, EmailRequest

# Constants
MIN_TITLE_LENGTH = 3


def _sanitize_api_title(title: str) -> str:
    """
    Sanitize API source titles to prevent exposing internal implementation details.

    Args:
        title: Raw title from tool or API

    Returns:
        str: Sanitized title suitable for user-facing references

    """
    if not title or not title.strip():
        return "External Data Source"

    sanitized = title.strip()

    # General cleanup for external APIs
    if "via RapidAPI" in sanitized:
        sanitized = sanitized.replace(" via RapidAPI", "")
    if "(RapidAPI)" in sanitized:
        sanitized = sanitized.replace(" (RapidAPI)", "")

    # Ensure we have a meaningful title
    if not sanitized or len(sanitized) < MIN_TITLE_LENGTH:
        sanitized = "External Data Source"

    return sanitized


class CitationManager:
    """Per-request citation manager without threading complexity."""

    def __init__(self):
        self._citations = CitationCollection()
        self._counter = 0
        self._url_to_id = {}  # Track URL to ID mapping for deduplication
        self._filename_to_id = {}  # Track filename to ID mapping for deduplication

    def add_web_source(self, url: str, title: str, description: str | None = None, *, visited: bool = False) -> str:
        """Add a web source and return its citation ID."""
        # Check if we already have this URL
        if url in self._url_to_id:
            existing_source = next((s for s in self._citations.sources if s.url == url), None)
            if existing_source and visited and not existing_source.description:
                # Update existing source to mark as visited if it wasn't before
                existing_source.description = "visited"
            return self._url_to_id[url]

        # Generate sequential ID
        self._counter += 1
        citation_id = str(self._counter)

        # Store URL mapping
        self._url_to_id[url] = citation_id

        # Set description based on whether it was visited or just searched
        if not description:
            description = "visited" if visited else "search result"

        source = CitationSource(
            id=citation_id,
            title=title,
            url=url,
            date_accessed=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            source_type="web",
            description=description
        )

        self._citations.add_source(source)
        return citation_id

    def add_attachment_source(self, filename: str, description: str | None = None) -> str:
        """Add an attachment source and return its citation ID."""
        # Check if we already have this filename
        if filename in self._filename_to_id:
            return self._filename_to_id[filename]

        # Generate sequential ID
        self._counter += 1
        citation_id = str(self._counter)

        # Store filename mapping
        self._filename_to_id[filename] = citation_id

        source = CitationSource(
            id=citation_id,
            title=filename,
            filename=filename,
            date_accessed=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            source_type="attachment",
            description=description or "processed attachment"
        )

        self._citations.add_source(source)
        return citation_id

    def add_api_source(self, title: str, description: str | None = None) -> str:
        """Add an API source and return its citation ID."""
        # Generate sequential ID (API sources are always unique)
        self._counter += 1
        citation_id = str(self._counter)

        # Sanitize the title to remove internal implementation details
        sanitized_title = _sanitize_api_title(title)

        source = CitationSource(
            id=citation_id,
            title=sanitized_title,
            date_accessed=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            source_type="api",
            description=description or "API data"
        )

        self._citations.add_source(source)
        return citation_id

    def get_citations(self) -> CitationCollection:
        """Get a copy of the current citations."""
        return CitationCollection(
            sources=self._citations.sources.copy(),
            references_section=self._citations.references_section
        )

    def generate_references_section(self) -> str:
        """Generate the formatted references section with improved formatting."""
        if not self._citations.sources:
            return ""

        # Categorize sources
        source_categories = {
            "visited": [],
            "search": [],
            "attachment": [],
            "api": []
        }

        for source in self._citations.sources:
            if source.source_type == "web":
                category = "visited" if source.description == "visited" else "search"
                source_categories[category].append(source)
            elif source.source_type == "attachment":
                source_categories["attachment"].append(source)
            else:
                source_categories["api"].append(source)

        # Build references section
        references = ["---", "", "### References"]

        # Add each category if it has sources
        section_configs = [
            ("visited", "#### Visited Pages", lambda s: f"{s.id}. [{s.title}]({s.url})"),
            ("search", "#### Search Results", lambda s: f"{s.id}. [{s.title}]({s.url})"),
            ("attachment", "#### Attachments", lambda s: f"{s.id}. {s.filename}"),
            ("api", "#### Data Sources", lambda s: f"{s.id}. {s.title}")
        ]

        for category, header, formatter in section_configs:
            if source_categories[category]:
                references.extend(["", header])
                references.extend(formatter(source) for source in source_categories[category])

        self._citations.references_section = "\n".join(references)
        return self._citations.references_section

    def has_citations(self) -> bool:
        """Check if there are any citations."""
        return len(self._citations.sources) > 0

    def reset(self) -> None:
        """Reset all citations."""
        self._citations = CitationCollection()
        self._counter = 0
        self._url_to_id = {}
        self._filename_to_id = {}


class RequestContext:
    """
    Centralized context for email request processing.

    Provides access to email request data, citations management,
    and other processing context in a clean, isolated manner.
    """

    def __init__(self, email_request: EmailRequest):
        """
        Initialize request context.

        Args:
            email_request: The email request being processed

        """
        self.email_request = email_request
        self.citation_manager = CitationManager()
        self.processing_metadata: dict[str, Any] = {}

    def get_attachment_paths(self) -> list[str]:
        """Get paths to persisted attachments."""
        if not self.email_request.attachments:
            return []
        return [att.path for att in self.email_request.attachments if att.path]

    def add_web_citation(self, url: str, title: str, description: str | None = None, *, visited: bool = False) -> str:
        """Add a web citation and return its ID."""
        return self.citation_manager.add_web_source(url, title, description, visited=visited)

    def add_attachment_citation(self, filename: str, description: str | None = None) -> str:
        """Add an attachment citation and return its ID."""
        return self.citation_manager.add_attachment_source(filename, description)

    def add_api_citation(self, title: str, description: str | None = None) -> str:
        """Add an API citation and return its ID."""
        return self.citation_manager.add_api_source(title, description)

    def has_citations(self) -> bool:
        """Check if any citations have been collected."""
        return self.citation_manager.has_citations()

    def get_references_section(self) -> str:
        """Get the formatted references section."""
        return self.citation_manager.generate_references_section()

    def get_citations(self) -> CitationCollection:
        """Get the citation collection."""
        return self.citation_manager.get_citations()
