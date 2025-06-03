import logging
import os
from typing import Any, Optional

import requests
from smolagents import Tool

logger = logging.getLogger(__name__)


class BraveSearchTool(Tool):
    """
    A tool for performing web searches using the Brave Search API.
    It requires the BRAVE_SEARCH_API_KEY environment variable to be set.
    """

    name: str = "brave_web_search"
    description: str = (
        "Performs a web search using the Brave Search API. "
        "Provide a query and it returns a list of search results with titles, snippets, and URLs. "
        "It can also provide a summary if available."
    )
    inputs: dict[str, dict[str, Any]] = {  # noqa: RUF012
        "query": {"type": "string", "description": "The search query to perform."}
    }
    output_type: str = "string"

    def __init__(self, api_key: str, max_results: int = 5):
        """
        Initializes the BraveSearchTool.

        Args:
            api_key: The Brave Search API key (X-Subscription-Token).
            max_results: The maximum number of search results to return.

        """
        super().__init__()
        if not api_key:
            msg = "Brave Search API key (X-Subscription-Token) is required."
            raise ValueError(msg)
        self.api_key = api_key
        self.max_results = max_results
        self.api_url = "https://api.search.brave.com/res/v1/web/search"

    def _parse_results(self, response_json: dict[str, Any]) -> str:
        """
        Parses the JSON response from Brave Search API and formats it into a string.
        """
        results_parts: list[str] = []

        # Attempt to extract summary
        summary_content = None
        summarizer_data = response_json.get("summarizer")
        if isinstance(summarizer_data, dict):
            # Common keys for summary text in such objects
            for key in ["text", "summary", "content", "answer"]:
                if isinstance(summarizer_data.get(key), str):
                    summary_content = summarizer_data[key]
                    break
            if not summary_content and isinstance(summarizer_data.get("results"), list):
                # Sometimes results are a list of summary segments
                summary_texts = [str(item) for item in summarizer_data["results"] if isinstance(item, str)]
                if summary_texts:
                    summary_content = "\n".join(summary_texts)
        elif isinstance(summarizer_data, str):
            summary_content = summarizer_data

        if summary_content:
            results_parts.append(f"Summary:\n{summary_content.strip()}\n\n---\n")

        web_results = response_json.get("web", {}).get("results", [])

        if not web_results and not summary_content:
            return "No results found."

        results_parts.append("Search Results:")
        for i, item in enumerate(web_results[: self.max_results]):
            title = item.get("title", "N/A")
            url = item.get("url", "N/A")
            snippet = item.get("description", item.get("snippet", "N/A"))

            results_parts.append(f"[{i + 1}] Title: {title}\nURL: {url}\nSnippet: {snippet}")

        return "\n\n".join(results_parts)

    def forward(self, query: str) -> str:
        """
        Executes the search query using the Brave Search API.

        Args:
            query: The search query.

        Returns:
            A string containing the formatted search results or an error message.

        Raises:
            Exception: If the API call fails or returns an error.

        """
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": query,
            "count": self.max_results,  # Specify number of results
            "summary": "true",  # Request a summary
            # "result_filter": "web", # Focus on web results if needed, helps simplify parsing
        }

        try:
            response = requests.get(self.api_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)

            response_json = response.json()

            # Check for explicit errors in Brave's response structure if any are defined
            # For example: if response_json.get("errors"): raise Exception(...)

            parsed_output = self._parse_results(response_json)
            if parsed_output == "No results found.":
                # This ensures SearchWithFallbackTool treats it as a failure
                msg = "No results found by Brave Search."
                raise Exception(msg)
            return parsed_output

        except requests.exceptions.HTTPError as http_err:
            logger.error(f"Brave Search API HTTP error: {http_err} - Response: {response.text}")
            msg = f"Brave Search API request failed with status {response.status_code}: {response.text}"
            raise Exception(msg) from http_err
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Brave Search API request error: {req_err}")
            msg = f"Brave Search API request failed: {req_err}"
            raise Exception(msg) from req_err
        except Exception as e:
            logger.error(f"Error processing Brave Search results: {e}")
            msg = f"Failed to process Brave Search results: {e!s}"
            raise Exception(msg) from e


# Helper function for EmailAgent to initialize this tool
def initialize_brave_search_tool(max_results: int = 5) -> Optional[BraveSearchTool]:
    """
    Initializes the BraveSearchTool if the API key is available.
    """
    api_key = os.getenv("BRAVE_SEARCH_API_KEY")
    if api_key:
        try:
            tool = BraveSearchTool(api_key=api_key, max_results=max_results)
            logger.debug("Initialized BraveSearchTool.")
            return tool
        except ValueError as e:
            logger.warning(f"Failed to initialize BraveSearchTool: {e}")
            return None
    else:
        logger.warning("BraveSearchTool not initialized. Missing BRAVE_SEARCH_API_KEY environment variable.")
        return None
