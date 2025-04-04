import logging
from typing import Optional

from smolagents import Tool

logger = logging.getLogger(__name__)

class FallbackWebSearchTool(Tool):
    """
    A web search tool that attempts a primary search tool (e.g., Google Search)
    and falls back to a secondary tool (e.g., DuckDuckGo) if the primary fails.
    """

    name = "web_search"
    description = "Performs a web search for your query then returns a string of the top search results. Attempts Google Search first if available, falling back to DuckDuckGo."
    inputs = {
        "query": {"type": "string", "description": "The search query to perform."},
    }
    output_type = "string"

    def __init__(
        self,
        primary_tool: Optional[Tool] = None,
        secondary_tool: Optional[Tool] = None,
    ):
        if not primary_tool and not secondary_tool:
            msg = "FallbackWebSearchTool requires at least one search tool."
            raise ValueError(msg)

        self.primary_tool = primary_tool
        self.secondary_tool = secondary_tool

        super().__init__()

    def forward(self, query: str) -> str:
        """
        Execute the search, attempting primary tool first, then secondary.
        """
        if self.primary_tool:
            try:
                logger.debug(f"Attempting search with primary tool: {self.primary_tool.name}")
                result = self.primary_tool.forward(query=query)
                logger.debug("Primary search tool succeeded.")
                return result
            except Exception as e:
                logger.warning(
                    f"Primary search tool ({self.primary_tool.name}) failed: {e!s}. "
                    f"Attempting fallback."
                )

        if self.secondary_tool:
            try:
                logger.debug(f"Attempting search with secondary tool: {self.secondary_tool.name}")
                result = self.secondary_tool.forward(query=query)
                logger.debug("Secondary search tool succeeded.")
                return result
            except Exception as e:
                logger.error(f"Secondary search tool ({self.secondary_tool.name}) also failed: {e!s}")
                msg = f"Both primary and secondary search tools failed. Last error: {e!s}"
                raise Exception(msg) from e
        else:
            # This case should ideally not be reached if primary failed and secondary doesn't exist
            logger.error("Primary search tool failed and no secondary tool is available.")
            msg = "Primary search tool failed and no fallback tool is configured."
            raise Exception(msg)
