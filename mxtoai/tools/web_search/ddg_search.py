"""
DuckDuckGo search tool - Free and fast search option.
"""

import json
import logging
import re

from smolagents import Tool
from smolagents.default_tools import WebSearchTool

from mxtoai.schemas import ToolOutputWithCitations
from mxtoai.scripts.citation_manager import add_web_citation

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
    inputs = {
        "query": {"type": "string", "description": "The search query to perform."},
    }
    output_type = "object"

    def __init__(self, max_results: int = 5):
        """
        Initialize DDG search tool.

        Args:
            max_results: Maximum number of results to return

        """
        self.max_results = max_results
        self.ddg_tool = WebSearchTool(engine="duckduckgo", max_results=max_results)
        super().__init__()
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
            for i, (title, url) in enumerate(matches[:self.max_results], 1):
                title = title.strip()
                url = url.strip()

                # Add citation for this result
                if url:
                    citation_id = add_web_citation(url, title, visited=False)
                    formatted_result = f"{i}. **{title}** [#{citation_id}]\n   URL: {url}\n"
                    citations_added += 1
                else:
                    formatted_result = f"{i}. **{title}**\n"

                formatted_results.append(formatted_result)

            # If no markdown links found, try to extract URLs directly
            if not formatted_results:
                logger.info("No markdown links found, trying direct URL extraction")
                url_pattern = r"https?://[^\s\n)]+"
                urls = re.findall(url_pattern, raw_result)

                for i, url in enumerate(urls[:self.max_results], 1):
                    # Generate a simple title from URL
                    title = url.split("/")[-1] or url.split("//")[-1].split("/")[0]
                    title = title.replace("-", " ").replace("_", " ").title()
                    if not title:
                        title = f"Search Result {i}"

                    citation_id = add_web_citation(url, title, visited=False)
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
            from mxtoai.schemas import CitationCollection

            # Create a local citation collection for this tool's output
            local_citations = CitationCollection()

            # Get only the citations that were added by this tool call
            # Since we track citations_added, we can get the last N citations
            if citations_added > 0:
                from mxtoai.scripts.citation_manager import get_citation_manager
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
                    "total_results": len(formatted_results) if formatted_results else 0,
                    "search_engine": "DuckDuckGo",
                    "citations_added": citations_added
                }
            )

            logger.info(f"DDG search completed successfully with {citations_added} citations")
            return json.dumps(result.model_dump())

        except Exception as e:
            logger.error(f"DDG search failed: {e}")
            raise
