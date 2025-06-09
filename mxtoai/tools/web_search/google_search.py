"""
Google search tool - Highest quality results with premium API cost.
"""

import logging
import os
from typing import Optional

from smolagents import Tool
from smolagents.default_tools import GoogleSearchTool as SmolagentsGoogleSearchTool

logger = logging.getLogger(__name__)


class GoogleSearchTool(Tool):
    """
    Google search tool - Highest quality results, premium API cost.
    Use only when DDG and Brave searches are insufficient for critical or complex queries.
    """

    name = "google_search"
    description = (
        "Performs a web search using Google Search API (SerpAPI or Serper). Use it when google results are needed"
        "It has premium API costs. Use this only when "
        "DDG and Brave searches are insufficient, or for critical/complex queries that require the best available information."
        "Ideal for authoritative sources, breaking news, and complex research topics."
    )
    inputs = {
        "query": {"type": "string", "description": "The search query to perform."},
    }
    output_type = "string"

    def __init__(self):
        """
        Initialize Google search tool.
        """
        self.google_tool: Optional[SmolagentsGoogleSearchTool] = None

        # Try to initialize Google search tool with available providers
        if os.getenv("SERPAPI_API_KEY"):
            try:
                self.google_tool = SmolagentsGoogleSearchTool(provider="serpapi")
                logger.debug("GoogleSearchTool initialized with SerpAPI")
            except ValueError as e:
                logger.warning(f"Failed to initialize GoogleSearchTool with SerpAPI: {e}")
        elif os.getenv("SERPER_API_KEY"):
            try:
                self.google_tool = SmolagentsGoogleSearchTool(provider="serper")
                logger.debug("GoogleSearchTool initialized with Serper")
            except ValueError as e:
                logger.warning(f"Failed to initialize GoogleSearchTool with Serper: {e}")

        if not self.google_tool:
            logger.warning("No Google Search API keys found. Google search will not be available.")

        super().__init__()

    def forward(self, query: str) -> str:
        """Execute Google search."""
        if not self.google_tool:
            msg = "Google Search API not configured. Cannot perform search."
            raise ValueError(msg)

        try:
            logger.info(f"Performing Google search for: {query}")
            result = self.google_tool.forward(query=query)
            logger.info("Google search completed successfully")
            return result
        except Exception as e:
            logger.error(f"Google search failed: {e}")
            raise
