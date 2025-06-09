"""
Brave search tool - Better quality results with moderate API cost.
"""

import logging
import os
from typing import Optional

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
        "query": {"type": "string", "description": "The user's search query term. Max 400 chars, 50 words."},
        "country": {"type": "string", "description": "2-char country code for results (e.g., 'US', 'DE'). Default: 'US'.", "nullable": True},
        "search_lang": {"type": "string", "description": "Language code for search results (e.g., 'en', 'es'). Default: 'en'.", "nullable": True},
        "ui_lang": {"type": "string", "description": "UI language for response (e.g., 'en-US'). Default: 'en-US'.", "nullable": True},
        "safesearch": {"type": "string", "description": "Filter adult content: 'off', 'moderate', 'strict'. Default: 'moderate'.", "nullable": True},
        "freshness": {"type": "string", "description": "Filter by discovery date: 'pd' (day), 'pw' (week), 'pm' (month), 'py' (year), or 'YYYY-MM-DDtoYYYY-MM-DD'. Default: None.", "nullable": True},
        "result_filter": {"type": "string", "description": "Comma-separated result types (e.g., 'web,news'). Default: 'web'.", "nullable": True},
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

    def forward(
        self,
        query: str,
        country: str = "US",
        search_lang: str = "en",
        ui_lang: str = "en-US",
        safesearch: str = "moderate",
        freshness: Optional[str] = None,
        result_filter: str = "web",
    ) -> str:
        """Execute Brave search."""
        if not self.api_key:
            msg = "Brave Search API key not configured. Cannot perform search."
            raise ValueError(msg)

        try:
            log_params = {
                "query": query,
                "country": country,
                "search_lang": search_lang,
                "ui_lang": ui_lang,
                "safesearch": safesearch,
                "freshness": freshness,
                "result_filter": result_filter,
            }
            logger.info(f"Performing Brave search with params: {log_params}")

            import requests

            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key,
            }

            params = {
                "q": query,
                "count": self.max_results,
                "country": country,
                "search_lang": search_lang,
                "ui_lang": ui_lang,
                "safesearch": safesearch,
                "result_filter": result_filter,
                "text_decorations": False,
                "spellcheck": True,
            }
            if freshness:
                params["freshness"] = freshness

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
