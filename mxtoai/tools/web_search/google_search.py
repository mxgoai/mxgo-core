"""
Google search tool - Highest quality results with premium API cost.
"""

import json
import logging
import os
import re
from typing import Optional

from smolagents import Tool
from smolagents.default_tools import GoogleSearchTool as SmolagentsGoogleSearchTool

from mxtoai.schemas import ToolOutputWithCitations
from mxtoai.scripts.citation_manager import add_web_citation

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
    output_type = "object"

    def __init__(self):
        """
        Initialize Google search tool.
        """
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

        super().__init__()

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
            for i, result_data in enumerate(results, 1):
                title = result_data.get('title', 'No title')
                url = result_data.get('url', '')

                # Add citation for this result
                if url:
                    citation_id = add_web_citation(url, title, visited=False)
                    formatted_result = f"{i}. **{title}** [#{citation_id}]\n   URL: {url}\n"
                else:
                    formatted_result = f"{i}. **{title}**\n"

                formatted_results.append(formatted_result)

            content = "\n".join(formatted_results)

            # Create structured output with local citations
            from mxtoai.schemas import CitationCollection
            from mxtoai.scripts.citation_manager import get_citation_manager

            # Create a local citation collection for this tool's output
            local_citations = CitationCollection()

            # Get only the citations that were added by this tool call
            citations_added = len(results)
            if citations_added > 0:
                global_citations = get_citation_manager().get_citations()
                # Get the last 'citations_added' number of citations
                recent_citations = global_citations.sources[-citations_added:] if global_citations.sources else []
                for citation in recent_citations:
                    local_citations.add_source(citation)

            result = ToolOutputWithCitations(
                content=content,
                citations=local_citations,
                metadata={
                    "query": query,
                    "total_results": len(results),
                    "search_engine": "Google",
                    "citations_added": citations_added
                }
            )

            logger.info("Google search completed successfully")
            return json.dumps(result.model_dump())

        except Exception as e:
            logger.error(f"Google search failed: {e}")
            raise
