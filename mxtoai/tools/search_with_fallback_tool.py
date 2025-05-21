import logging
from typing import Optional, List

from smolagents import Tool

logger = logging.getLogger(__name__)

class SearchWithFallbackTool(Tool):
    """
    A web search tool that attempts a sequence of primary search tools
    and falls back to another tool if all primary attempts fail.
    """

    name = "web_search"  # Consistent name for the agent to use
    description = (
        "Performs a web search using a sequence of search engines. "
        "It first attempts searches with primary engines (e.g., Bing, DuckDuckGo). "
        "If all primary searches fail or yield no results, it attempts a fallback engine (e.g., Google Search)."
        "If everything fails, rephrase the query and try again."
    )
    inputs = {
        "query": {"type": "string", "description": "The search query to perform."},
    }
    output_type = "string"

    def __init__(
        self,
        primary_search_tools: List[Tool],
        fallback_search_tool: Optional[Tool] = None,
    ):
        """
        Initializes the SearchWithFallbackTool.

        Args:
            primary_search_tools: A list of Tool instances to try in order as primary searchers.
            fallback_search_tool: An optional Tool instance to use if all primary tools fail.
        """
        if not primary_search_tools and not fallback_search_tool:
            raise ValueError("SearchWithFallbackTool requires at least one primary or fallback search tool.")

        self.primary_search_tools = primary_search_tools if primary_search_tools else []
        if not self.primary_search_tools:
            logger.warning(
                "SearchWithFallbackTool initialized without any primary search tools. "
                "It will only use the fallback tool if available and primary attempts are implicitly skipped."
            )

        self.fallback_search_tool = fallback_search_tool
        super().__init__()

    def _get_tool_identifier(self, tool_instance: Tool, default_name: str) -> str:
        """Helper to get a descriptive name for a tool instance for logging."""
        base_name = getattr(tool_instance, 'name', default_name)
        if hasattr(tool_instance, 'engine'): # Specifically for WebSearchTool
            return f"{base_name} (engine: {tool_instance.engine})"
        return base_name

    def forward(self, query: str) -> str:
        """
        Execute the search, trying primary tools first, then the fallback tool.
        """
        # Try primary search tools in order
        for i, tool_instance in enumerate(self.primary_search_tools):
            tool_identifier = self._get_tool_identifier(tool_instance, f"PrimaryTool_{i+1}")
            try:
                logger.debug(f"Attempting search with primary tool: {tool_identifier}")
                result = tool_instance.forward(query=query)
                # Underlying smolagents tools typically raise exceptions if no results are found.
                # So, a successful return here implies results were found.
                logger.info(f"Primary search tool {tool_identifier} succeeded.")
                return result
            except Exception as e:
                logger.warning(
                    f"Primary search tool {tool_identifier} failed: {e!s}. "
                    f"Trying next primary tool or fallback."
                )

        # If all primary tools failed, try the fallback tool
        if self.fallback_search_tool:
            fallback_tool_instance = self.fallback_search_tool
            tool_identifier = self._get_tool_identifier(fallback_tool_instance, "FallbackTool")
            try:
                logger.debug(f"Attempting search with fallback tool: {tool_identifier}")
                result = fallback_tool_instance.forward(query=query)
                logger.info(f"Fallback search tool {tool_identifier} succeeded.")
                return result
            except Exception as e:
                logger.error(f"Fallback search tool ({tool_identifier}) also failed: {e!s}")
                # Ensure the original exception 'e' from the fallback tool is part of the new exception context
                raise SearchFailureException(
                    f"All primary search tools failed, and the fallback search tool ({tool_identifier}) also failed. Last error: {e!s}"
                ) from e
        else:
            logger.error("All primary search tools failed and no fallback tool is configured.")
            # It's important to raise an exception here if no tools succeeded and no fallback was available or fallback also failed.
            raise SearchFailureException("All primary search tools failed and no fallback tool is configured or the fallback also failed.")
