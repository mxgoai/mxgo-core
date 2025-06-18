"""
Global Citation Manager for collecting and managing citations across tools.

This module provides a thread-safe global citation manager that can be used
across different tools to collect citations and generate references.
"""

import threading
from datetime import datetime
from typing import Optional

from mxtoai.schemas import CitationCollection, CitationSource


def _sanitize_api_title(title: str) -> str:
    """
    Sanitize API source titles to prevent exposing internal implementation details.
    Now minimal since LinkedIn tools use actual profile URLs as web citations.

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
    if not sanitized or len(sanitized) < 3:
        sanitized = "External Data Source"

    return sanitized


class GlobalCitationManager:
    """Thread-safe global citation manager."""

    def __init__(self):
        self._citations = CitationCollection()
        self._lock = threading.Lock()
        self._counter = 0
        self._url_to_id = {}  # Track URL to ID mapping for deduplication
        self._filename_to_id = {}  # Track filename to ID mapping for deduplication

    def add_web_source(self, url: str, title: str, description: Optional[str] = None, visited: bool = False) -> str:
        """Add a web source and return its citation ID."""
        with self._lock:
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
                date_accessed=datetime.now().strftime("%Y-%m-%d"),
                source_type="web",
                description=description
            )

            self._citations.add_source(source)
            return citation_id

    def add_attachment_source(self, filename: str, description: Optional[str] = None) -> str:
        """Add an attachment source and return its citation ID."""
        with self._lock:
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
                date_accessed=datetime.now().strftime("%Y-%m-%d"),
                source_type="attachment",
                description=description or "processed attachment"
            )

            self._citations.add_source(source)
            return citation_id

    def add_api_source(self, title: str, description: Optional[str] = None) -> str:
        """
        Add an API source and return its citation ID.

        Args:
            title: Title of the API source (will be sanitized to remove internal details)
            description: Optional description

        Returns:
            str: Citation ID
        """
        with self._lock:
            # Generate sequential ID (API sources are always unique)
            self._counter += 1
            citation_id = str(self._counter)

            # Sanitize the title to remove internal implementation details
            sanitized_title = _sanitize_api_title(title)

            source = CitationSource(
                id=citation_id,
                title=sanitized_title,
                date_accessed=datetime.now().strftime("%Y-%m-%d"),
                source_type="api",
                description=description or "API data"
            )

            self._citations.add_source(source)
            return citation_id

    def get_citations(self) -> CitationCollection:
        """Get a copy of the current citations."""
        with self._lock:
            return CitationCollection(
                sources=self._citations.sources.copy(),
                references_section=self._citations.references_section
            )

    def generate_references_section(self) -> str:
        """Generate the formatted references section with improved formatting."""
        with self._lock:
            if not self._citations.sources:
                return ""

            # Separate visited pages from search results
            visited_sources = []
            search_sources = []
            attachment_sources = []
            api_sources = []

            for source in self._citations.sources:
                if source.source_type == "web":
                    if source.description == "visited":
                        visited_sources.append(source)
                    else:
                        search_sources.append(source)
                elif source.source_type == "attachment":
                    attachment_sources.append(source)
                else:
                    api_sources.append(source)

            # Build references section with horizontal line
            references = ["---", "", "### References"]

            # Add visited pages first (highest priority)
            if visited_sources:
                references.append("")
                references.append("#### Visited Pages")
                for source in visited_sources:
                    ref = f"{source.id}. [{source.title}]({source.url})"
                    references.append(ref)

            # Add search results (lower priority, more condensed)
            if search_sources:
                references.append("")
                references.append("#### Search Results")
                for source in search_sources:
                    ref = f"{source.id}. [{source.title}]({source.url})"
                    references.append(ref)

            # Add attachments
            if attachment_sources:
                references.append("")
                references.append("#### Attachments")
                for source in attachment_sources:
                    ref = f"{source.id}. {source.filename}"
                    references.append(ref)

            # Add API sources
            if api_sources:
                references.append("")
                references.append("#### Data Sources")
                for source in api_sources:
                    ref = f"{source.id}. {source.title}"
                    references.append(ref)

            self._citations.references_section = "\n".join(references)
            return self._citations.references_section

    def reset(self) -> None:
        """Reset all citations (useful for new conversations)."""
        with self._lock:
            self._citations = CitationCollection()
            self._counter = 0
            self._url_to_id = {}
            self._filename_to_id = {}

    def has_citations(self) -> bool:
        """Check if there are any citations."""
        with self._lock:
            return len(self._citations.sources) > 0


# Global singleton instance
_global_citation_manager = GlobalCitationManager()


def get_citation_manager() -> GlobalCitationManager:
    """Get the global citation manager instance."""
    return _global_citation_manager


def reset_citations() -> None:
    """Reset all citations (convenience function)."""
    _global_citation_manager.reset()


def add_web_citation(url: str, title: str, description: Optional[str] = None, visited: bool = False) -> str:
    """Add a web citation (convenience function)."""
    return _global_citation_manager.add_web_source(url, title, description, visited)


def add_attachment_citation(filename: str, description: Optional[str] = None) -> str:
    """Add an attachment citation (convenience function)."""
    return _global_citation_manager.add_attachment_source(filename, description)


def add_api_citation(title: str, description: Optional[str] = None) -> str:
    """
    Add an API citation (convenience function).

    Args:
        title: Title of the API source (will be sanitized automatically)
        description: Optional description

    Returns:
        str: Citation ID

    Example:
        # Instead of exposing internal details:
        add_api_citation("LinkedIn Fresh Data API Tool via RapidAPI")

        # Use user-friendly titles:
        add_api_citation("LinkedIn Profile Data")
    """
    return _global_citation_manager.add_api_source(title, description)


def get_references_section() -> str:
    """Get the formatted references section (convenience function)."""
    return _global_citation_manager.generate_references_section()