import logging
from typing import ClassVar

from smolagents import Tool

logger = logging.getLogger(__name__)


class FallbackSearchError(Exception):
    """Base exception for fallback search tool errors."""


class FallbackWebSearchTool(Tool):
    """
    A web search tool that attempts a primary search tool (e.g., Google Search)
    and falls back to a secondary tool (e.g., DuckDuckGo) if the primary fails.
    """

    name = "web_search"
    description = "Performs a web search for your query then returns a string of the top search results. Attempts Google Search first if available, falling back to DuckDuckGo."
    inputs: ClassVar[dict] = {
        "query": {"type": "string", "description": "The search query to perform."},
    }
    output_type = "string"

    def __init__(
        self,
        primary_tool: Tool | None = None,
        secondary_tool: Tool | None = None,
    ):
        """
        Initialize the FallbackWebSearchTool.

        Args:
            primary_tool: The primary search tool to use (e.g., GoogleSearchTool).
            secondary_tool: The secondary search tool to use if the primary fails (e.g., DuckDuckGoSearchTool).

        """
        if not primary_tool and not secondary_tool:
            msg = "FallbackWebSearchTool requires at least one search tool."
            raise ValueError(msg)

        self.primary_tool = primary_tool
        self.secondary_tool = secondary_tool

        super().__init__()

    def forward(self, query: str) -> str:
        """
        Execute the search, attempting primary tool first, then secondary.

        Args:
            query: The search query to perform.

        Returns:
            str: The search results from the successful tool.

        """
        if self.primary_tool:
            try:
                logger.debug(f"Attempting search with primary tool: {self.primary_tool.name}")
                result = self.primary_tool.forward(query=query)
                logger.debug("Primary search tool succeeded.")
            except Exception as e:
                logger.warning(f"Primary search tool ({self.primary_tool.name}) failed: {e!s}. Attempting fallback.")
            else:
                return result

        if self.secondary_tool:
            try:
                logger.debug(f"Attempting search with secondary tool: {self.secondary_tool.name}")
                result = self.secondary_tool.forward(query=query)
                logger.debug("Secondary search tool succeeded.")
            except Exception as e:
                logger.error(f"Secondary search tool ({self.secondary_tool.name}) also failed: {e!s}")
                msg = f"Both primary and secondary search tools failed. Last error: {e!s}"
                raise FallbackSearchError(msg) from e
            else:
                return result
        else:
            # This case should ideally not be reached if primary failed and secondary doesn't exist
            logger.error("Primary search tool failed and no secondary tool is available.")
            msg = "Primary search tool failed and no fallback tool is configured."
            raise FallbackSearchError(msg)
