"""
News search tool for personalized news updates on specific topics.

This tool provides access to Brave Search News API to retrieve current news articles
based on search queries, with support for time-based filtering and geographical targeting.
"""

import json
import os
from typing import ClassVar

import requests
from smolagents import Tool

from mxtoai._logging import get_logger
from mxtoai.request_context import RequestContext
from mxtoai.schemas import CitationCollection, ToolOutputWithCitations

logger = get_logger(__name__)


class NewsTool(Tool):
    """
    News search tool that provides personalized news updates on specific topics.

    Uses Brave Search News API to retrieve current news articles with flexible
    query capabilities including time-based filtering and geographical targeting.

    Key features:
    - Retrieve daily news updates on specific topics
    - Time-based news filtering (past day, week, month, year, or custom date range)
    - Geographical targeting by country
    - Breaking news identification
    - Source attribution and age information
    """

    name = "news_search"
    description = (
        "Search for current news articles on specific topics using Brave Search News API. "
        "Perfect for getting personalized news updates, stock news, geopolitical updates, "
        "technology news, and more. Supports time-based filtering to get news from specific "
        "time periods (past day, week, month, year, or custom date ranges). "
        "Use this when users need current, fresh news information on any topic."
    )
    inputs: ClassVar[dict] = {
        "query": {
            "type": "string",
            "description": "The news search query. Be specific (e.g., 'Tesla stock earnings', 'Ukraine conflict latest', 'AI developer tools reviews'). Max 400 chars."
        },
        "freshness": {
            "type": "string",
            "description": "Time filter for news freshness: 'pd' (past day), 'pw' (past week), 'pm' (past month), 'py' (past year), or 'YYYY-MM-DDtoYYYY-MM-DD' for custom date range. Default: 'pw' (past week).",
            "nullable": True,
        },
        "country": {
            "type": "string",
            "description": "2-character country code for localized news (e.g., 'US', 'DE', 'GB', 'IN'). Default: 'US'.",
            "nullable": True,
        },
        "search_lang": {
            "type": "string",
            "description": "Language code for search results (e.g., 'en', 'es', 'fr', 'de'). Default: 'en'.",
            "nullable": True,
        },
        "count": {
            "type": "integer",
            "description": "Number of news articles to return (1-20). Default: 10.",
            "nullable": True,
        }
    }
    output_type = "object"

    def __init__(self, context: RequestContext, max_results: int = 10):
        """
        Initialize News search tool.

        Args:
            context: Request context containing email data and citation manager
            max_results: Maximum number of news articles to return (default: 10)

        """
        self.context = context
        self.max_results = max_results
        self.api_key = os.getenv("BRAVE_SEARCH_API_KEY")
        super().__init__()

        if not self.api_key:
            logger.warning("BRAVE_SEARCH_API_KEY not found. News search will not be available.")
        else:
            logger.debug(f"NewsTool initialized with max_results={max_results}")

    def forward(
        self,
        query: str,
        freshness: str = "pw",
        country: str = "US",
        search_lang: str = "en",
        count: int | None = None,
    ) -> str:
        """
        Search for news articles and return results with citations.

        Args:
            query: The news search query
            freshness: Time filter for news freshness (default: "pw" - past week)
            country: Country code for localized news (default: "US")
            search_lang: Language code for search results (default: "en")
            count: Number of results to return (default: uses max_results)

        Returns:
            JSON string containing formatted news results with citations

        Raises:
            ValueError: If API key is not configured

        """
        if not self.api_key:
            msg = "Brave Search API key not configured. Cannot perform news search."
            raise ValueError(msg)

        # Use provided count or default max_results, but cap at 20
        result_count = min(count or self.max_results, 20)

        try:
            log_params = {
                "query": query,
                "freshness": freshness,
                "country": country,
                "search_lang": search_lang,
                "count": result_count,
            }
            logger.info(f"Performing news search with params: {log_params}")

            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self.api_key,
            }

            params = {
                "q": query,
                "count": result_count,
                "country": country,
                "search_lang": search_lang,
                "freshness": freshness,
                "spellcheck": True,
            }

            response = requests.get(
                "https://api.search.brave.com/res/v1/news/search",
                headers=headers,
                params=params,
                timeout=15,
            )
            response.raise_for_status()

            data = response.json()
            logger.debug(f"News API response received: {data.get('type', 'unknown')} type")

            # Process news results
            results = data.get("results", [])
            if not results:
                logger.warning(f"No news results found for query: {query}")
                result = ToolOutputWithCitations(
                    content=f"No news articles found for query: '{query}' with freshness filter: {freshness}",
                    metadata={
                        "query": query,
                        "total_results": 0,
                        "freshness": freshness,
                        "country": country,
                    }
                )
                return json.dumps(result.model_dump())

            # Format news results
            content_parts = []
            content_parts.append(f"**News Results for '{query}'** (Freshness: {freshness}, Country: {country})")
            content_parts.append("")

            citations_added = 0
            for i, article in enumerate(results, 1):
                title = article.get("title", "No title")
                url = article.get("url", "")
                description = article.get("description", "No description")
                age = article.get("age", "")
                page_age = article.get("page_age", "")

                # Check for breaking news or other special attributes
                extra_info = []
                if age:
                    extra_info.append(f"Published: {age}")
                if page_age and page_age != age:
                    extra_info.append(f"Page age: {page_age}")

                # Check if this might be breaking news (recently published)
                is_recent = any(indicator in (age or "").lower() for indicator in ["hour", "minute", "now", "just"])

                # Format the result
                formatted_result = f"{i}. **{title}**"
                if is_recent:
                    formatted_result += " 🔴 **RECENT**"

                if extra_info:
                    formatted_result += f" *({', '.join(extra_info)})*"

                formatted_result += f"\n   {description}"

                # Add citation if URL is available
                if url:
                    citation_id = self.context.add_web_citation(url, f"{title} (News)", visited=False)
                    formatted_result += f"\n   📰 Source: {url} [#{citation_id}]"
                    citations_added += 1

                content_parts.append(formatted_result)
                content_parts.append("")  # Add spacing between articles

            content = "\n".join(content_parts).strip()

            # Create local citation collection for this tool's output
            local_citations = CitationCollection()
            if citations_added > 0:
                # Get the recent citations added by this tool call
                context_citations = self.context.get_citations()
                recent_citations = context_citations.sources[-citations_added:] if context_citations.sources else []
                for citation in recent_citations:
                    local_citations.add_source(citation)

            # Determine freshness description for metadata
            freshness_map = {
                "pd": "Past day",
                "pw": "Past week",
                "pm": "Past month",
                "py": "Past year"
            }
            freshness_desc = freshness_map.get(freshness, freshness)

            result = ToolOutputWithCitations(
                content=content,
                citations=local_citations,
                metadata={
                    "query": query,
                    "total_results": len(results),
                    "freshness": freshness,
                    "freshness_description": freshness_desc,
                    "country": country,
                    "search_lang": search_lang,
                    "citations_added": citations_added,
                    "search_engine": "Brave News",
                    "api_endpoint": "news/search",
                }
            )

            logger.info(f"News search completed successfully: {len(results)} articles found, {citations_added} citations added")
            return json.dumps(result.model_dump())

        except requests.RequestException as e:
            error_msg = f"News search request failed: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e
        except Exception as e:
            error_msg = f"News search failed: {e}"
            logger.error(error_msg)
            raise ValueError(error_msg) from e
