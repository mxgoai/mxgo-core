"""
Custom agent types for citation handling that extend smolagents functionality.
"""

import json
from typing import Any, Dict

from smolagents.agent_types import AgentType

from mxtoai.schemas import ToolOutputWithCitations


class AgentCitationOutput(AgentType):
    """
    Citation-aware output type for smolagents that preserves citation metadata.
    """

    def __init__(self, value: Any):
        """
        Initialize with either a ToolOutputWithCitations object or raw data.

        Args:
            value: Either a ToolOutputWithCitations object, dict, or string
        """
        super().__init__(value)

        if isinstance(value, ToolOutputWithCitations):
            self._citations_output = value
            self._content = value.content
        elif isinstance(value, dict):
            try:
                self._citations_output = ToolOutputWithCitations(**value)
                self._content = self._citations_output.content
            except Exception:
                # Fallback for non-citation dict
                self._citations_output = None
                self._content = json.dumps(value) if value else ""
        elif isinstance(value, str):
            try:
                # Try to parse as JSON first
                parsed = json.loads(value)
                if isinstance(parsed, dict) and "content" in parsed:
                    self._citations_output = ToolOutputWithCitations(**parsed)
                    self._content = self._citations_output.content
                else:
                    self._citations_output = None
                    self._content = value
            except (json.JSONDecodeError, Exception):
                # Treat as plain string
                self._citations_output = None
                self._content = value
        else:
            self._citations_output = None
            self._content = str(value)

    def to_raw(self) -> Any:
        """Return the raw content without citation metadata."""
        return self._content

    def to_string(self) -> str:
        """Return the string representation of the content."""
        return str(self._content)

    def get_citations(self) -> Dict[str, Any]:
        """Get citation metadata if available."""
        if self._citations_output:
            return {
                "citations": self._citations_output.citations.model_dump(),
                "metadata": self._citations_output.metadata
            }
        return {}

    def has_citations(self) -> bool:
        """Check if this output contains citations."""
        return (
            self._citations_output is not None and
            len(self._citations_output.citations.sources) > 0
        )


def handle_citation_outputs(output: Any) -> Any:
    """
    Handle outputs that might contain citations.

    This function can be used as a post-processing step for tool outputs
    to preserve citation information while maintaining compatibility.

    Args:
        output: Tool output that might contain citations

    Returns:
        Processed output with citation handling
    """
    if isinstance(output, (dict, str)) and _looks_like_citation_output(output):
        return AgentCitationOutput(output)
    return output


def _looks_like_citation_output(value: Any) -> bool:
    """Check if a value looks like a citation output."""
    if isinstance(value, dict):
        return "content" in value and ("citations" in value or "metadata" in value)
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
            return isinstance(parsed, dict) and "content" in parsed
        except (json.JSONDecodeError, Exception):
            return False
    return False