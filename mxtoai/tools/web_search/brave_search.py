"""
Brave search tool - Better quality results with moderate API cost.
"""

import logging
import os
from smolagents import Tool

logger = logging.getLogger(__name__)


class BraveSearchTool(Tool):
    """
    Brave search tool - Better quality results than DDG, moderate API cost.
    Use when DDG results are insufficient or when you need more comprehensive information.
    """

    name = "brave_search"
    description = (
        "Performs a web search using Brave Search API. You can do Web search, Images, Videos, News, and more."
        "It might give better results than DuckDuckGo but has moderate API costs. Use this when DDG results are insufficient "
        "or when you need more detailed, current, or specialized information. Good for research and detailed queries."
    )
    inputs = {
        "query": {"type": "string", "description": "The search query to perform."},
    }
    output_type = "string"

    def __init__(self, max_results: int = 5):
        """
        Initialize Brave search tool.

        Args:
            max_results: Maximum number of results to return
        """
        self.max_results = max_results
        self.api_key = os.getenv("BRAVE_SEARCH_API_KEY")
        super().__init__()

        if not self.api_key:
            logger.warning("BRAVE_SEARCH_API_KEY not found. Brave search will not be available.")
        else:
            logger.debug(f"BraveSearchTool initialized with max_results={max_results}")

    def forward(self, query: str) -> str:
        """Execute Brave search."""
        if not self.api_key:
            raise ValueError("Brave Search API key not configured. Cannot perform search.")

        try:
            logger.info(f"Performing Brave search for: {query}")

            import requests

            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key,
            }

            params = {
                "q": query,
                "count": self.max_results,
                "offset": 0,
                "mkt": "en-US",
                "safesearch": "moderate",
                "freshness": "pd",  # Past day for freshness
                "text_decorations": False,
                "spellcheck": True,
            }

            response = requests.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            web_results = data.get("web", {}).get("results", [])

            if not web_results:
                logger.warning(f"Brave search returned no results for query: {query}")
                return f"No results found for query: {query}"

            # Format results
            formatted_results = []
            for i, result in enumerate(web_results[:self.max_results], 1):
                title = result.get("title", "No title")
                url = result.get("url", "")
                description = result.get("description", "No description")

                formatted_result = f"{i}. **{title}**\n   URL: {url}\n   {description}\n"
                formatted_results.append(formatted_result)

            result_text = "\n".join(formatted_results)
            logger.info("Brave search completed successfully")
            return result_text

        except Exception as e:
            logger.error(f"Brave search failed: {e}")
            raise