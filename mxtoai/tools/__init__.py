# Tools package for email processing
import os
from collections.abc import Callable

from smolagents import Tool
from smolagents.default_tools import PythonInterpreterTool, WikipediaSearchTool

from mxtoai._logging import get_logger
from mxtoai.request_context import RequestContext
from mxtoai.routed_litellm_model import RoutedLiteLLMModel
from mxtoai.schemas import ToolName
from mxtoai.scripts.visual_qa import AzureVisualizerTool, HuggingFaceVisualizerTool, OpenAIVisualizerTool
from mxtoai.tools.attachment_processing_tool import AttachmentProcessingTool
from mxtoai.tools.cancel_subscription_tool import CancelSubscriptionTool
from mxtoai.tools.citation_aware_visit_tool import CitationAwareVisitTool
from mxtoai.tools.deep_research_tool import DeepResearchTool
from mxtoai.tools.delete_scheduled_tasks_tool import DeleteScheduledTasksTool
from mxtoai.tools.external_data.linkedin.fresh_data import LinkedInFreshDataTool
from mxtoai.tools.external_data.linkedin.linkedin_data_api import LinkedInDataAPITool
from mxtoai.tools.fallback_search_tool import FallbackWebSearchTool
from mxtoai.tools.meeting_tool import MeetingTool
from mxtoai.tools.news_tool import NewsTool
from mxtoai.tools.pdf_export_tool import PDFExportTool
from mxtoai.tools.references_generator_tool import ReferencesGeneratorTool
from mxtoai.tools.scheduled_tasks_tool import ScheduledTasksTool
from mxtoai.tools.web_search import BraveSearchTool, DDGSearchTool, GoogleSearchTool

__all__ = [
    "AttachmentProcessingTool",
    "AzureVisualizerTool",
    "BraveSearchTool",
    "CancelSubscriptionTool",
    "CitationAwareVisitTool",
    "DDGSearchTool",
    "DeepResearchTool",
    "DeleteScheduledTasksTool",
    "FallbackWebSearchTool",
    "GoogleSearchTool",
    "HuggingFaceVisualizerTool",
    "LinkedInDataAPITool",
    "LinkedInFreshDataTool",
    "MeetingTool",
    "NewsTool",
    "OpenAIVisualizerTool",
    "PDFExportTool",
    "ReferencesGeneratorTool",
    "ScheduledTasksTool",
    "create_tool_mapping",
]


def _initialize_search_tools(context: RequestContext) -> dict[ToolName, Tool | None]:
    """Initialize search tools."""
    tool_mapping = {}
    tool_mapping[ToolName.DDG_SEARCH] = DDGSearchTool(context=context, max_results=10)

    if os.getenv("BRAVE_SEARCH_API_KEY"):
        tool_mapping[ToolName.BRAVE_SEARCH] = BraveSearchTool(context=context, max_results=5)
        tool_mapping[ToolName.NEWS_SEARCH] = NewsTool(context=context, max_results=10)
    else:
        tool_mapping[ToolName.BRAVE_SEARCH] = None
        tool_mapping[ToolName.NEWS_SEARCH] = None

    primary_search_tool = tool_mapping.get(ToolName.BRAVE_SEARCH) or tool_mapping.get(ToolName.DDG_SEARCH)

    if primary_search_tool:
        try:
            fallback_search_tool = FallbackWebSearchTool(
                primary_tool=primary_search_tool,
                secondary_tool=tool_mapping.get(ToolName.DDG_SEARCH)
                if primary_search_tool == tool_mapping.get(ToolName.BRAVE_SEARCH)
                else None,
            )
            tool_mapping[ToolName.WEB_SEARCH] = fallback_search_tool
        except Exception:
            tool_mapping[ToolName.WEB_SEARCH] = primary_search_tool
    else:
        tool_mapping[ToolName.WEB_SEARCH] = None

    if os.getenv("SERPAPI_API_KEY") or os.getenv("SERPER_API_KEY"):
        tool_mapping[ToolName.GOOGLE_SEARCH] = GoogleSearchTool(context=context)
    else:
        tool_mapping[ToolName.GOOGLE_SEARCH] = None
    return tool_mapping


def _initialize_linkedin_tools(context: RequestContext) -> dict[ToolName, Tool | None]:
    """Initialize LinkedIn tools."""
    tool_mapping = {}
    rapidapi_key = os.getenv("RAPIDAPI_KEY")
    if rapidapi_key:
        try:
            tool_mapping[ToolName.LINKEDIN_FRESH_DATA] = LinkedInFreshDataTool(api_key=rapidapi_key, context=context)
        except Exception:
            tool_mapping[ToolName.LINKEDIN_FRESH_DATA] = None
        try:
            tool_mapping[ToolName.LINKEDIN_DATA_API] = LinkedInDataAPITool(api_key=rapidapi_key, context=context)
        except Exception:
            tool_mapping[ToolName.LINKEDIN_DATA_API] = None
    else:
        tool_mapping[ToolName.LINKEDIN_FRESH_DATA] = None
        tool_mapping[ToolName.LINKEDIN_DATA_API] = None
    return tool_mapping


def create_tool_mapping(
    context: RequestContext,
    scheduled_tasks_tool_factory: Callable[[], Tool],
    allowed_python_imports: list[str],
    model: RoutedLiteLLMModel | None = None,
) -> dict[ToolName, Tool | None]:
    """
    Create a mapping of ToolName enums to actual tool instances.

    Args:
        context: Request context for tools that need it
        scheduled_tasks_tool_factory: Factory function to create limited scheduled tasks tool
        allowed_python_imports: List of allowed Python imports for the interpreter
        model: Optional RoutedLiteLLMModel instance for tools that need it

    Returns:
        dict[ToolName, Tool | None]: Mapping of tool names to instances

    """
    if model is None:
        model = RoutedLiteLLMModel()

    tool_mapping = {
        ToolName.ATTACHMENT_PROCESSOR: AttachmentProcessingTool(context=context),
        ToolName.CITATION_AWARE_VISIT: CitationAwareVisitTool(context=context),
        ToolName.PYTHON_INTERPRETER: PythonInterpreterTool(authorized_imports=allowed_python_imports),
        ToolName.WIKIPEDIA_SEARCH: WikipediaSearchTool(),
        ToolName.REFERENCES_GENERATOR: ReferencesGeneratorTool(context=context),
    }

    try:
        tool_mapping[ToolName.AZURE_VISUALIZER] = AzureVisualizerTool(model=model)
    except Exception as e:
        tool_mapping[ToolName.AZURE_VISUALIZER] = None
        logger = get_logger("tools")
        logger.warning(f"Failed to initialize AzureVisualizerTool: {e}")

    tool_mapping.update(_initialize_search_tools(context))
    tool_mapping.update(_initialize_linkedin_tools(context))

    if os.getenv("JINA_API_KEY"):
        tool_mapping[ToolName.DEEP_RESEARCH] = DeepResearchTool()
    else:
        tool_mapping[ToolName.DEEP_RESEARCH] = None

    tool_mapping[ToolName.MEETING_CREATOR] = MeetingTool()
    tool_mapping[ToolName.PDF_EXPORT] = PDFExportTool()
    tool_mapping[ToolName.SCHEDULED_TASKS] = scheduled_tasks_tool_factory()
    tool_mapping[ToolName.DELETE_SCHEDULED_TASKS] = DeleteScheduledTasksTool(context=context)
    tool_mapping[ToolName.CANCEL_SUBSCRIPTION_TOOL] = CancelSubscriptionTool()

    return tool_mapping
