# Tools package for email processing
import os
from collections.abc import Callable

from smolagents import Tool
from smolagents.default_tools import PythonInterpreterTool, WikipediaSearchTool

from mxtoai.request_context import RequestContext
from mxtoai.schemas import ToolName
from mxtoai.scripts.visual_qa import azure_visualizer
from mxtoai.tools.attachment_processing_tool import AttachmentProcessingTool
from mxtoai.tools.citation_aware_visit_tool import CitationAwareVisitTool
from mxtoai.tools.deep_research_tool import DeepResearchTool
from mxtoai.tools.delete_scheduled_tasks_tool import DeleteScheduledTasksTool
from mxtoai.tools.external_data.linkedin.fresh_data import LinkedInFreshDataTool
from mxtoai.tools.external_data.linkedin.linkedin_data_api import LinkedInDataAPITool
from mxtoai.tools.meeting_tool import MeetingTool
from mxtoai.tools.pdf_export_tool import PDFExportTool
from mxtoai.tools.references_generator_tool import ReferencesGeneratorTool
from mxtoai.tools.scheduled_tasks_tool import ScheduledTasksTool
from mxtoai.tools.web_search import BraveSearchTool, DDGSearchTool, GoogleSearchTool

__all__ = [
    "AttachmentProcessingTool",
    "BraveSearchTool",
    "CitationAwareVisitTool",
    "DDGSearchTool",
    "DeepResearchTool",
    "DeleteScheduledTasksTool",
    "GoogleSearchTool",
    "LinkedInDataAPITool",
    "LinkedInFreshDataTool",
    "MeetingTool",
    "PDFExportTool",
    "ReferencesGeneratorTool",
    "ScheduledTasksTool",
    "create_tool_mapping",
]


def create_tool_mapping(
    context: RequestContext,
    scheduled_tasks_tool_factory: Callable[[], Tool],
    allowed_python_imports: list[str],
) -> dict[ToolName, Tool | None]:
    """
    Create a mapping of ToolName enums to actual tool instances.

    Args:
        context: Request context for tools that need it
        scheduled_tasks_tool_factory: Factory function to create limited scheduled tasks tool
        allowed_python_imports: List of allowed Python imports for the interpreter

    Returns:
        dict[ToolName, Tool | None]: Mapping of tool names to instances

    """
    tool_mapping = {}

    # Common tools
    tool_mapping[ToolName.ATTACHMENT_PROCESSOR] = AttachmentProcessingTool(context=context)
    tool_mapping[ToolName.CITATION_AWARE_VISIT] = CitationAwareVisitTool(context=context)
    tool_mapping[ToolName.PYTHON_INTERPRETER] = PythonInterpreterTool(authorized_imports=allowed_python_imports)
    tool_mapping[ToolName.WIKIPEDIA_SEARCH] = WikipediaSearchTool()
    tool_mapping[ToolName.REFERENCES_GENERATOR] = ReferencesGeneratorTool(context=context)
    tool_mapping[ToolName.AZURE_VISUALIZER] = azure_visualizer

    # Search tools
    tool_mapping[ToolName.DDG_SEARCH] = DDGSearchTool(context=context, max_results=10)

    # Conditional search tools (based on API key availability)
    if os.getenv("BRAVE_SEARCH_API_KEY"):
        tool_mapping[ToolName.BRAVE_SEARCH] = BraveSearchTool(context=context, max_results=5)
    else:
        tool_mapping[ToolName.BRAVE_SEARCH] = None

    if os.getenv("SERPAPI_API_KEY") or os.getenv("SERPER_API_KEY"):
        tool_mapping[ToolName.GOOGLE_SEARCH] = GoogleSearchTool(context=context)
    else:
        tool_mapping[ToolName.GOOGLE_SEARCH] = None

    # Specialized tools
    if os.getenv("JINA_API_KEY"):
        tool_mapping[ToolName.DEEP_RESEARCH] = DeepResearchTool()
    else:
        tool_mapping[ToolName.DEEP_RESEARCH] = None

    tool_mapping[ToolName.MEETING_CREATOR] = MeetingTool()
    tool_mapping[ToolName.PDF_EXPORT] = PDFExportTool()
    tool_mapping[ToolName.SCHEDULED_TASKS] = scheduled_tasks_tool_factory()
    tool_mapping[ToolName.DELETE_SCHEDULED_TASKS] = DeleteScheduledTasksTool(context=context)

    # LinkedIn tools (conditional on API key)
    rapidapi_key = os.getenv("RAPIDAPI_KEY")
    if rapidapi_key:
        try:
            tool_mapping[ToolName.LINKEDIN_FRESH_DATA] = LinkedInFreshDataTool(api_key=rapidapi_key, context=context)
        except Exception:
            # Silently fail and set to None - caller will handle logging
            tool_mapping[ToolName.LINKEDIN_FRESH_DATA] = None

        try:
            tool_mapping[ToolName.LINKEDIN_DATA_API] = LinkedInDataAPITool(api_key=rapidapi_key, context=context)
        except Exception:
            # Silently fail and set to None - caller will handle logging
            tool_mapping[ToolName.LINKEDIN_DATA_API] = None
    else:
        tool_mapping[ToolName.LINKEDIN_FRESH_DATA] = None
        tool_mapping[ToolName.LINKEDIN_DATA_API] = None

    return tool_mapping
