"""
Citation-aware wrapper tools for the Email Deep Research Agent.

This module provides wrapper classes that extend the original tools but collect URL
information for a simple references section without embedding citations in text.
"""

import re
from typing import Optional

from smolagents import GoogleSearchTool

from .text_web_browser import VisitTool

# Global store for all URLs visited during research
_all_visited_urls: list[str] = []


def reset_citation_counter():
    """Reset the global URL store."""
    _all_visited_urls.clear()


def add_to_citation_store(url: str) -> None:
    """
    Add a URL to the global references collection.

    Args:
        url: URL of the source
        title: Title of the source (optional)
        date: Publication date (optional)

    """
    # Don't add duplicates
    if url not in _all_visited_urls:
        _all_visited_urls.append(url)


def get_all_visited_urls() -> list[str]:
    return _all_visited_urls


class CitationAwareGoogleSearchTool(GoogleSearchTool):
    """
    Extension of GoogleSearchTool that collects URL information.
    """

    def forward(self, query: str, filter_year: Optional[int] = None) -> str:
        """
        Perform a Google search and collect URL information.

        Args:
            query: Search query
            filter_year: Optional year filter

        Returns:
            Original search results

        """
        # Get original results
        original_results = super().forward(query, filter_year)

        # Extract URLs from search results
        urls = re.findall(r"\[.*?\]\((https?://.*?)\)", original_results)

        # Extract titles alongside URLs where possible
        title_url_matches = re.findall(r"\[(.*?)\]\((https?://.*?)\)", original_results)

        # Add URLs to the global collection
        for match in title_url_matches:
            title, url = match
            add_to_citation_store(url=url)

        # Add any URLs that didn't have a title match
        for url in urls:
            if url not in _all_visited_urls:
                add_to_citation_store(url=url)

        return original_results


class CitationAwareVisitTool(VisitTool):
    """
    Extension of VisitTool that collects URL information.
    """

    def forward(self, url: str) -> str:
        """
        Visit a webpage and collect URL information.

        Args:
            url: URL to visit

        Returns:
            Original webpage content

        """
        # Get original content
        original_content = super().forward(url)

        # Extract title if present
        title_match = (
            re.search(r"<title>(.*?)</title>", original_content)
            or re.search(r"<h1>(.*?)</h1>", original_content)
            or re.search(r"# (.*?)$", original_content, re.MULTILINE)
        )

        title_match.group(1) if title_match else None

        # Add URL to the global collection
        add_to_citation_store(url=url)

        return original_content


def extract_citations() -> dict[str, dict[str, str]]:
    """
    Maintained for backward compatibility.
    This function no longer extracts citations but returns an empty dict.

    Returns:
        Empty dictionary

    """
    return {}


def create_references_section() -> str:
    """
    Create a properly formatted references section from all collected URLs.

    Returns:
        Formatted references section

    """
    if not _all_visited_urls:
        return ""

    references = ["## References"]

    # Sort references by timestamp (newest first)
    sorted_urls = sorted(_all_visited_urls, key=lambda x: x["timestamp"], reverse=True)

    for i, url_info in enumerate(sorted_urls, 1):
        title = url_info.get("title", url_info["url"])
        url = url_info["url"]
        date = url_info.get("date", "n.d.")

        # Format reference
        reference = f"{i}. *{title}*. Retrieved on {date} from [{url}]({url})"
        references.append(reference)

    return "\n\n".join(references)
