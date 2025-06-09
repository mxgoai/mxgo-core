"""
DuckDuckGo search tool - Free and fast search option.
"""

import logging

from smolagents import Tool
from smolagents.default_tools import WebSearchTool

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
    output_type = "string"

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
        """Execute DuckDuckGo search."""
        try:
            logger.info(f"Performing DDG search for: {query}")
            result = self.ddg_tool.forward(query=query)
            logger.info("DDG search completed successfully")
            return result
        except Exception as e:
            logger.error(f"DDG search failed: {e}")
            raise
