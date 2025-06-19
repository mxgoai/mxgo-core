"""
Google search tool using SerpAPI or Serper APIs - Premium results with higher costs.
"""

import json
import logging
import os
import re
from typing import Optional

from smolagents import Tool
from smolagents.default_tools import GoogleSearchTool as SmolagentsGoogleSearchTool

from mxtoai.request_context import RequestContext
from mxtoai.schemas import ToolOutputWithCitations

logger = logging.getLogger(__name__)


class GoogleSearchTool(Tool):
    """
    Google search tool using premium APIs - Best quality results with higher costs.
    Uses SerpAPI or Serper for Google search. Requires API keys.
    """

    name = "google_search"
    description = (
        "Performs web search using Google Search APIs (SerpAPI/Serper). This provides the highest quality "
        "and most comprehensive search results but also has the highest cost. Use this when you need "
        "the most authoritative, current, or specialized information that might not be found with other search engines."
    )
    inputs = {
        "query": {"type": "string", "description": "The search query to perform."},
    }
    output_type = "string"

    def __init__(self, context: RequestContext):
        """
        Initialize Google search tool.

        Args:
            context: Request context containing email data and citation manager
        """
        super().__init__()
        self.context = context
        self.google_tool: Optional[SmolagentsGoogleSearchTool] = None

        # Try to initialize Google search tool with available providers
        # Try SerpAPI first if available
        if os.getenv("SERPAPI_API_KEY"):
            try:
                self.google_tool = SmolagentsGoogleSearchTool(provider="serpapi")
                logger.debug("GoogleSearchTool initialized with SerpAPI")
            except ValueError as e:
                logger.warning(f"Failed to initialize GoogleSearchTool with SerpAPI: {e}")

        # If SerpAPI failed or not available, try Serper
        if not self.google_tool and os.getenv("SERPER_API_KEY"):
            try:
                self.google_tool = SmolagentsGoogleSearchTool(provider="serper")
                logger.debug("GoogleSearchTool initialized with Serper")
            except ValueError as e:
                logger.warning(f"Failed to initialize GoogleSearchTool with Serper: {e}")

        if not self.google_tool:
            logger.warning("No Google Search API keys found. Google search will not be available.")

    def forward(self, query: str) -> str:
        """Execute Google search and return results with citations."""
        if not self.google_tool:
            msg = "Google Search API not configured. Cannot perform search."
            raise ValueError(msg)

        try:
            logger.info(f"Performing Google search for: {query}")
            raw_result = self.google_tool.forward(query=query)

            # Parse the raw result to extract URLs and titles
            # Google results typically come in markdown format with links
            results = []

            # Extract markdown links: [title](url)
            link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
            matches = re.findall(link_pattern, raw_result)

            for title, url in matches:
                results.append({
                    'title': title.strip(),
                    'url': url.strip()
                })

            if not results:
                # Fallback: treat the whole result as content
                result = ToolOutputWithCitations(
                    content=raw_result,
                    metadata={"query": query, "total_results": 0, "search_engine": "Google"}
                )
                logger.info("Google search completed (no structured results found)")
                return json.dumps(result.model_dump())

            # Format results with citations
            formatted_results = []
            citations_added = 0

            for i, result_item in enumerate(results, 1):
                title = result_item['title']
                url = result_item['url']

                # Add citation for this result
                if url:
                    citation_id = self.context.add_web_citation(url, title, visited=False)
                    formatted_result = f"{i}. **{title}** [#{citation_id}]\n   URL: {url}\n"
                else:
                    formatted_result = f"{i}. **{title}**\n"

                formatted_results.append(formatted_result)
                citations_added += 1

            # Create content with citations
            content = "## Search Results\n\n" + "\n".join(formatted_results)

            result = ToolOutputWithCitations(
                content=content,
                metadata={
                    "query": query,
                    "total_results": len(results),
                    "search_engine": "Google",
                    "citations_added": citations_added
                }
            )

            logger.info(f"Google search completed successfully with {citations_added} citations")
            return json.dumps(result.model_dump())

        except Exception as e:
            logger.error(f"Google search failed: {e}")
            raise
