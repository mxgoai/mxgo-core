"""
DuckDuckGo search tool - Free and fast search option.
"""

import json
import logging
import re
from typing import ClassVar

from smolagents import Tool
from smolagents.default_tools import WebSearchTool

from mxtoai.request_context import RequestContext
from mxtoai.schemas import CitationCollection, ToolOutputWithCitations

logger = logging.getLogger(__name__)


class DDGSearchTool(Tool):
    """
    DuckDuckGo search tool - Free and fast, but may have limited results.
    Use this first for most queries as it's cost-effective.
    """

    name = "ddg_search"
    description = (
        "Performs a web search using DuckDuckGo. This is the most cost-effective search option "
        "and should be tried first for most queries. It's free but may have limited or less comprehensive results "
        "compared to premium search engines. Good for general information and quick searches."
    )
    inputs: ClassVar[dict] = {
        "query": {"type": "string", "description": "The search query to perform."},
    }
    output_type = "object"

    def __init__(self, context: RequestContext, max_results: int = 5):
        """
        Initialize DDG search tool.

        Args:
            context: Request context containing email data and citation manager
            max_results: Maximum number of results to return

        """
        super().__init__()
        self.context = context
        self.max_results = max_results
        self.ddg_tool = WebSearchTool(engine="duckduckgo", max_results=max_results)
        logger.debug(f"DDGSearchTool initialized with max_results={max_results}")

    def forward(self, query: str) -> str:
        """Execute DuckDuckGo search and return results with citations."""
        try:
            logger.info(f"Performing DDG search for: {query}")
            raw_result = self.ddg_tool.forward(query=query)

            # Log the raw result to understand its format
            logger.debug(f"DDG raw result: {raw_result[:500]}...")  # Log first 500 chars

            # Extract markdown links from the raw result: [title](url)
            link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"
            matches = re.findall(link_pattern, raw_result)

            formatted_results = []
            citations_added = 0

            # Process each markdown link found
            for i, (link_title, link_url) in enumerate(matches[: self.max_results], 1):
                clean_title = link_title.strip()
                clean_url = link_url.strip()

                # Add citation for this result
                if clean_url:
                    citation_id = self.context.add_web_citation(clean_url, clean_title, visited=False)
                    formatted_result = f"{i}. **{clean_title}** [#{citation_id}]\n   URL: {clean_url}\n"
                    citations_added += 1
                else:
                    formatted_result = f"{i}. **{clean_title}**\n"

                formatted_results.append(formatted_result)

            # If no markdown links found, try to extract URLs directly
            if not formatted_results:
                logger.info("No markdown links found, trying direct URL extraction")
                url_pattern = r"https?://[^\s\n)]+"
                urls = re.findall(url_pattern, raw_result)

                for i, url in enumerate(urls[: self.max_results], 1):
                    # Generate a simple title from URL
                    title = url.split("/")[-1] or url.split("//")[-1].split("/")[0]
                    title = title.replace("-", " ").replace("_", " ").title()
                    if not title:
                        title = f"Search Result {i}"

                    citation_id = self.context.add_web_citation(url, title, visited=False)
                    formatted_result = f"{i}. **{title}** [#{citation_id}]\n   URL: {url}\n"
                    formatted_results.append(formatted_result)
                    citations_added += 1

            # Create content with citations
            if formatted_results:
                content = "## Search Results\n\n" + "\n".join(formatted_results)
                # Also include the original content for context
                content += f"\n\n### Additional Context\n{raw_result}"
            else:
                logger.info("Using raw content as fallback")
                content = f"## Search Results\n\n{raw_result}"

            # Create structured output with local citations
            # Create a local citation collection for this tool's output
            local_citations = CitationCollection()

            # Get only the citations that were added by this tool call
            if citations_added > 0:
                global_citations = self.context.get_citations()
                # Get the last 'citations_added' number of citations
                recent_citations = global_citations.sources[-citations_added:] if global_citations.sources else []
                for citation in recent_citations:
                    local_citations.add_source(citation)

            result = ToolOutputWithCitations(
                content=content,
                citations=local_citations,
                metadata={
                    "query": query,
                    "total_results": len(formatted_results) if formatted_results else 0,
                    "search_engine": "DuckDuckGo",
                    "citations_added": citations_added,
                },
            )

            logger.info(f"DDG search completed successfully with {citations_added} citations")
            return json.dumps(result.model_dump())

        except Exception as e:
            logger.error(f"DDG search failed: {e}")
            raise
