import ast
import os
import re
import tomllib  # For Python 3.11+
from datetime import datetime
from typing import Any, Optional, Union
import contextlib # Added import

from dotenv import load_dotenv
from mcp import StdioServerParameters
from smolagents import Tool, ToolCallingAgent
from smolagents.default_tools import (
    GoogleSearchTool,
    PythonInterpreterTool,
    VisitWebpageTool,
    WebSearchTool,
    WikipediaSearchTool,
)

from mxtoai._logging import get_logger
from mxtoai.mcp import load_mcp_tools_from_config
from mxtoai.models import ProcessingInstructions
from mxtoai.prompts.base_prompts import (
    LIST_FORMATTING_REQUIREMENTS,
    MARKDOWN_STYLE_GUIDE,
    RESEARCH_GUIDELINES,
    RESPONSE_GUIDELINES,
)
from mxtoai.routed_litellm_model import RoutedLiteLLMModel
from mxtoai.schemas import (
    AgentResearchMetadata,
    AgentResearchOutput,
    AttachmentsProcessingResult,
    CalendarResult,
    DetailedEmailProcessingResult,
    EmailAttachment,
    EmailContentDetails,
    EmailRequest,
    EmailSentStatus,
    ProcessedAttachmentDetail,
    ProcessingError,
    ProcessingMetadata,
)
from mxtoai.scripts.report_formatter import ReportFormatter
from mxtoai.scripts.visual_qa import azure_visualizer
from mxtoai.tools.attachment_processing_tool import AttachmentProcessingTool
from mxtoai.tools.deep_research_tool import DeepResearchTool
from mxtoai.tools.schedule_tool import ScheduleTool
from mxtoai.tools.search_with_fallback_tool import SearchWithFallbackTool
# Import the new Brave Search tool
from mxtoai.tools.brave_search_tool import initialize_brave_search_tool

# Load environment variables
load_dotenv(override=True)

# Configure logger
logger = get_logger("email_agent")

# Define allowed imports for PythonInterpreterTool
ALLOWED_PYTHON_IMPORTS = [
    "datetime",
    "pytz",
    "math",
    "json",
    "re",
    "time",
    "collections",
    "itertools",
    "xml.etree.ElementTree",
    "csv",
    "urllib.parse",
]


class EmailAgent:
    """
    Email processing agent that can summarize, reply to, and research information for emails.
    """

    def __init__(
        self,
        attachment_dir: str = "email_attachments",
        verbose: bool = False,
        enable_deep_research: bool = False,
    ):
        """
        Initialize the email agent with tools for different operations.

        Args:
            attachment_dir: Directory to store email attachments.
            verbose: Whether to enable verbose logging.
            enable_deep_research: Whether to enable Jina AI deep research functionality (uses API tokens).
        """
        if verbose:
            logger.debug("Verbose logging potentially enabled (actual level depends on logger config).")

        self.attachment_dir = attachment_dir
        os.makedirs(self.attachment_dir, exist_ok=True)

        # Initialize base tools (non-MCP)
        self.attachment_tool = AttachmentProcessingTool()
        self.report_formatter = ReportFormatter()
        self.schedule_tool = ScheduleTool()
        self.visit_webpage_tool = VisitWebpageTool()
        self.python_tool = PythonInterpreterTool(authorized_imports=ALLOWED_PYTHON_IMPORTS)
        self.wikipedia_search_tool = WikipediaSearchTool()
        self.search_with_fallback_tool = self._initialize_search_tools()
        self.research_tool = self._initialize_deep_research_tool(enable_deep_research)

        self.base_tools: list[Tool] = [
            self.attachment_tool,
            self.schedule_tool,
            self.visit_webpage_tool,
            self.search_with_fallback_tool,
            self.python_tool,
            self.wikipedia_search_tool,
            azure_visualizer,
        ]
        if self.research_tool:
            self.base_tools.append(self.research_tool)
        
        self.routed_model = RoutedLiteLLMModel() # Keep routed model initialization

        tool_names = [tool.name for tool in self.base_tools]
        logger.info(f"Base agent tools initialized: {tool_names}")
        logger.info("Email agent initialized (MCP tools will be loaded dynamically per request)")

    def _get_mcp_servers_config(self) -> dict[str, dict[str, Any]]:
        """
        Parses the mcp.toml file and returns server configurations
        for enabled MCP servers.
        """
        effective_mcp_config_path = os.getenv("MCP_CONFIG_PATH", "mcp.toml")

        if not os.path.exists(effective_mcp_config_path):
            logger.debug(f"MCP configuration file not found at '{effective_mcp_config_path}'. No MCP tools will be loaded.")
            return {}

        try:
            with open(effective_mcp_config_path, "rb") as f:
                config = tomllib.load(f)
        except tomllib.TOMLDecodeError as e:
            logger.error(f"Error decoding MCP TOML file at '{effective_mcp_config_path}': {e}")
            return {}
        except OSError as e:
            logger.error(f"Error reading MCP TOML file at '{effective_mcp_config_path}': {e}")
            return {}

        mcp_servers_config = config.get("mcp_servers", {})
        if not mcp_servers_config:
            logger.info(f"No 'mcp_servers' table found in '{effective_mcp_config_path}'. No MCP tools will be loaded.")
            return {}

        # Filter for enabled servers and merge environment variables
        enabled_servers = {}
        for server_name, server_details in mcp_servers_config.items():
            if not server_details.get("enabled", True):  # Default to enabled if not specified
                logger.debug(f"MCP server '{server_name}' is disabled in config. Skipping.")
                continue

            # Create a copy and merge environment variables for stdio servers
            server_config = server_details.copy()
            if server_config.get("type") == "stdio" and "env" in server_config:
                # Merge with current environment
                server_config["env"] = {**os.environ, **server_config["env"]}
            
            enabled_servers[server_name] = server_config

        logger.info(f"Found {len(enabled_servers)} enabled MCP servers in configuration.")
        return enabled_servers

    def _initialize_search_tools(self) -> SearchWithFallbackTool:
        """
        Initializes and configures the search tools, returning the SearchWithFallbackTool.
        The order of preference is DuckDuckGo, then Brave Search, then Google Search as fallback.

        Returns:
            SearchWithFallbackTool: The configured search tool.
        """
        ddg_search_tool = WebSearchTool(engine="duckduckgo", max_results=5)
        logger.debug("Initialized WebSearchTool with DuckDuckGo engine.")

        brave_search_tool = initialize_brave_search_tool(max_results=5)
        # No need to log here as initialize_brave_search_tool does it.

        google_search_fallback_tool = self._initialize_google_search_tool()
        # No need to log here as _initialize_google_search_tool does it.

        primary_search_engines: list[Tool] = []
        if ddg_search_tool: # ddg_search_tool is always initialized
            primary_search_engines.append(ddg_search_tool)
        if brave_search_tool: # brave_search_tool might be None if API key is missing
            primary_search_engines.append(brave_search_tool)

        if not primary_search_engines:
             logger.warning(
                "No primary search engines (DuckDuckGo, Brave) could be initialized for SearchWithFallbackTool."
            )

        search_tool = SearchWithFallbackTool(
            primary_search_tools=primary_search_engines, fallback_search_tool=google_search_fallback_tool
        )

        primary_names = [getattr(p, "name", "UnknownTool") for p in primary_search_engines]
        fallback_name = getattr(google_search_fallback_tool, "name", "None") if google_search_fallback_tool else "None"
        logger.info(
            f"Initialized SearchWithFallbackTool. Primary engines: {primary_names}, Fallback: {fallback_name}"
        )
        return search_tool

    def _get_required_actions(self, mode: str) -> list[str]:
        """
        Get list of required actions based on mode.

        Args:
            mode: The mode of operation (e.g., "summary", "reply", "research", "full").

        Returns:
            List of actions to be performed by the agent.
        """
        actions = []
        if mode in ["summary", "full"]:
            actions.append("Generate summary")
        if mode in ["reply", "full"]:
            actions.append("Generate reply")
        if mode in ["research", "full"]:
            actions.append("Conduct research")
        return actions

    def _initialize_google_search_tool(self) -> Optional[GoogleSearchTool]:
        """
        Initialize Google search tool with either SerpAPI or Serper provider.

        Returns:
            Optional[GoogleSearchTool]: Initialized GoogleSearchTool instance or None if fails.
        """
        if os.getenv("SERPAPI_API_KEY"):
            try:
                tool = GoogleSearchTool(provider="serpapi")
                logger.debug("Initialized GoogleSearchTool with SerpAPI for fallback.")
                return tool
            except ValueError as e:
                logger.warning(f"Failed to initialize GoogleSearchTool with SerpAPI: {e}")
        elif os.getenv("SERPER_API_KEY"):
            try:
                tool = GoogleSearchTool(provider="serper")
                logger.debug("Initialized GoogleSearchTool with Serper for fallback.")
                return tool
            except ValueError as e:
                logger.warning(f"Failed to initialize GoogleSearchTool with Serper: {e}")
        else:
            logger.warning("GoogleSearchTool (fallback) not initialized: SERPAPI_API_KEY or SERPER_API_KEY missing.")
        return None

    def _initialize_deep_research_tool(self, enable_deep_research: bool) -> Optional[DeepResearchTool]:
        """
        Initializes the DeepResearchTool if API key is available.

        Args:
            enable_deep_research: Flag to enable deep research functionality.

        Returns:
            Optional[DeepResearchTool]: Initialized DeepResearchTool instance or None.
        """
        if not os.getenv("JINA_API_KEY"):
            logger.info("JINA_API_KEY not found. DeepResearchTool not initialized.")
            return None

        research_tool = DeepResearchTool()
        if enable_deep_research:
            logger.debug(
                "DeepResearchTool instance created; deep research functionality is active."
            )
        else:
            logger.debug(
                "DeepResearchTool instance created, but deep research is not explicitly enabled via agent config."
            )
        return research_tool

    def _create_task(self, email_request: EmailRequest, email_instructions: ProcessingInstructions) -> str:
        """
        Create a task description for the agent based on email handle instructions.

        Args:
            email_request: EmailRequest instance containing email data.
            email_instructions: EmailHandleInstructions object with processing configuration.

        Returns:
            The task description for the agent.
        """
        attachments = []
        if email_instructions.process_attachments and email_request.attachments:
            attachments = self._format_attachments(email_request.attachments)

        return self._create_task_template(
            handle=email_instructions.handle,
            email_context=self._create_email_context(email_request, attachments),
            handle_specific_template=email_instructions.task_template,
            attachment_task=self._create_attachment_task(attachments),
            deep_research_mandatory=email_instructions.deep_research_mandatory,
            output_template=email_instructions.output_template,
        )

    def _format_attachments(self, attachments: list[EmailAttachment]) -> list[str]:
        """
        Format attachment details for inclusion in the task.

        Args:
            attachments: List of EmailAttachment objects.

        Returns:
            List of formatted attachment details.
        """
        return [
            f'- {att.filename} (Type: {att.contentType}, Size: {att.size} bytes)\n  EXACT FILE PATH: "{att.path}"'
            for att in attachments
        ]

    def _create_email_context(self, email_request: EmailRequest, attachment_details: Optional[list[str]] = None) -> str:
        """
        Generate context information from the email request.

        Args:
            email_request: EmailRequest instance containing email data.
            attachment_details: List of formatted attachment details.

        Returns:
            The context information for the agent.
        """
        recipients = ", ".join(email_request.recipients) if email_request.recipients else "N/A"
        attachments_info = (
            f"Available Attachments:\n{chr(10).join(attachment_details)}"
            if attachment_details
            else "No attachments provided."
        )
        body_content = email_request.textContent or email_request.htmlContent or ""
        return f"""Email Content:
    Subject: {email_request.subject}
    From: {email_request.from_email}
    Email Date: {email_request.date}
    Recipients: {recipients}
    CC: {email_request.cc or "N/A"}
    BCC: {email_request.bcc or "N/A"}
    Body: {body_content}

    {attachments_info}
    """

    def _create_attachment_task(self, attachment_details: list[str]) -> str:
        """
        Return instructions for processing attachments, if any.

        Args:
            attachment_details: List of formatted attachment details.

        Returns:
            Instructions for processing attachments.
        """
        return f"Process these attachments:\n{chr(10).join(attachment_details)}" if attachment_details else ""

    def _create_task_template(
        self,
        handle: str,
        email_context: str,
        handle_specific_template: str = "",
        attachment_task: str = "",
        deep_research_mandatory: bool = False,
        output_template: str = "",
    ) -> str:
        """
        Combine all task components into the final task description.
        """
        research_guideline = RESEARCH_GUIDELINES["mandatory"] if deep_research_mandatory else RESEARCH_GUIDELINES["optional"]
        sections = [
            f"Process this email according to the '{handle}' instruction type.\n",
            email_context,
            research_guideline,
            attachment_task,
            handle_specific_template,
            output_template,
            RESPONSE_GUIDELINES,
            MARKDOWN_STYLE_GUIDE,
            LIST_FORMATTING_REQUIREMENTS,
        ]
        return "\n\n".join(filter(None, sections))

    def _process_agent_result(
        self, final_answer_obj: Any, agent_steps: list, current_email_handle: str
    ) -> DetailedEmailProcessingResult:
        processed_at_time = datetime.now().isoformat()

        errors_list: list[ProcessingError] = []
        email_sent_status = EmailSentStatus(status="pending", timestamp=processed_at_time)
        attachment_proc_summary: Optional[str] = None
        processed_attachment_details: list[ProcessedAttachmentDetail] = []
        calendar_result_data: Optional[CalendarResult] = None
        research_output_findings: Optional[str] = None
        research_output_metadata: Optional[AgentResearchMetadata] = None
        final_answer_from_llm: Optional[str] = None
        email_text_content: Optional[str] = None
        email_html_content: Optional[str] = None

        try:
            logger.debug(f"Processing final answer object type: {type(final_answer_obj)}")
            logger.debug(f"Processing {len(agent_steps)} agent step entries.")

            for i, step in enumerate(agent_steps):
                logger.debug(f"[Memory Step {i + 1}] Type: {type(step)}")
                tool_name: Optional[str] = None
                tool_output: Any = None

                if hasattr(step, "tool_calls") and isinstance(step.tool_calls, list) and step.tool_calls:
                    first_tool_call = step.tool_calls[0]
                    tool_name = getattr(first_tool_call, "name", None)
                    if not tool_name:
                        logger.warning(f"[Memory Step {i + 1}] Could not extract tool name from first call.")
                    action_out = getattr(step, "action_output", None)
                    obs_out = getattr(step, "observations", None)
                    tool_output = action_out if action_out is not None else obs_out

                if tool_name and tool_output is not None:
                    needs_parsing = tool_name in ["schedule_generator", "attachment_processor", "deep_research"]
                    if isinstance(tool_output, str) and needs_parsing:
                        try:
                            tool_output = ast.literal_eval(tool_output)
                        except (ValueError, SyntaxError) as e:
                            msg = (
                                f"[Memory Step {i + 1}] Failed to parse '{tool_name}' output: {e!s}. "
                                f"Content: {tool_output[:200]}..."
                            )
                            logger.error(msg)
                            errors_list.append(
                                ProcessingError(message=f"Failed to parse {tool_name} output", details=str(e))
                            )
                            continue
                        except Exception as e: # pylint: disable=broad-except
                            msg = (
                                f"[Memory Step {i + 1}] Unexpected error parsing '{tool_name}' output: {e!s}. "
                                f"Content: {tool_output[:200]}..."
                            )
                            logger.error(msg)
                            errors_list.append(
                                ProcessingError(message=f"Unexpected error parsing {tool_name} output", details=str(e))
                            )
                            continue

                    logger.debug(
                        f"[Memory Step {i + 1}] Processing tool call: '{tool_name}', "
                        f"Output Type: '{type(tool_output)}'"
                    )

                    if tool_name == "attachment_processor" and isinstance(tool_output, dict):
                        attachment_proc_summary = tool_output.get("summary")
                        for attachment_data in tool_output.get("attachments", []):
                            pa_detail = ProcessedAttachmentDetail(
                                filename=attachment_data.get("filename", "unknown.file"),
                                size=attachment_data.get("size", 0),
                                type=attachment_data.get("type", "unknown"),
                            )
                            if "error" in attachment_data:
                                pa_detail.error = attachment_data["error"]
                                errors_list.append(
                                    ProcessingError(
                                        message=f"Error processing attachment {pa_detail.filename}",
                                        details=pa_detail.error,
                                    )
                                )
                            if "content" in attachment_data and isinstance(attachment_data["content"], dict):
                                if attachment_data["content"].get("caption"):
                                    pa_detail.caption = attachment_data["content"]["caption"]
                            processed_attachment_details.append(pa_detail)

                    elif tool_name == "deep_research" and isinstance(tool_output, dict):
                        research_output_findings = tool_output.get("findings")
                        research_output_metadata = AgentResearchMetadata(
                            query=tool_output.get("query"),
                            annotations=tool_output.get("annotations", []),
                            visited_urls=tool_output.get("visited_urls", []),
                            read_urls=tool_output.get("read_urls", []),
                            timestamp=tool_output.get("timestamp"),
                            usage=tool_output.get("usage", {}),
                            num_urls=tool_output.get("num_urls", 0),
                        )
                        if not research_output_findings:
                            errors_list.append(ProcessingError(message="Deep research tool returned empty findings."))

                    elif tool_name == "schedule_generator" and isinstance(tool_output, dict):
                        if tool_output.get("status") == "success" and tool_output.get("ics_content"):
                            calendar_result_data = CalendarResult(ics_content=tool_output["ics_content"])
                        else:
                            error_msg = tool_output.get("message", "Schedule generator failed or missing ICS content.")
                            errors_list.append(ProcessingError(message="Schedule Tool Error", details=error_msg))
                    else:
                        logger.debug(
                            f"[Memory Step {i + 1}] Tool '{tool_name}' output processed (no specific handler). "
                            f"Output: {str(tool_output)[:200]}..."
                        )
                else:
                    logger.debug(
                        f"[Memory Step {i + 1}] Skipping step (Type: {type(step)}), "
                        "not a relevant ActionStep or missing output."
                    )

            if hasattr(final_answer_obj, "text"):
                final_answer_from_llm = str(final_answer_obj.text).strip()
                logger.debug("Extracted final answer from AgentResponse.text")
            elif isinstance(final_answer_obj, str):
                final_answer_from_llm = final_answer_obj.strip()
                logger.debug("Extracted final answer from string")
            elif hasattr(final_answer_obj, "_value"):  # Check for older AgentText structure
                final_answer_from_llm = str(final_answer_obj._value).strip()
                logger.debug("Extracted final answer from AgentText._value")
            elif hasattr(final_answer_obj, "answer"):
                if isinstance(getattr(final_answer_obj, "answer", None), str):
                    final_answer_from_llm = str(final_answer_obj.answer).strip()
                    logger.debug("Extracted final answer from final_answer tool argument string")
                elif (
                    isinstance(getattr(final_answer_obj, "arguments", None), dict)
                    and "answer" in final_answer_obj.arguments
                ):
                    final_answer_from_llm = str(final_answer_obj.arguments["answer"]).strip()
                    logger.debug("Extracted final answer from final_answer tool arguments dict")
                else:
                    final_answer_from_llm = str(final_answer_obj).strip()
                    logger.warning(
                        f"Could not find specific answer attribute in final_answer object, using str(). "
                        f"Result: {final_answer_from_llm[:100]}..."
                    )
            else:
                final_answer_from_llm = str(final_answer_obj).strip()
                logger.warning(
                    f"Could not find specific answer attribute in final_answer object, using str(). "
                    f"Result: {final_answer_from_llm[:100]}..."
                )

            email_body_content_source = research_output_findings if research_output_findings else final_answer_from_llm

            if email_body_content_source:
                signature_markers = [
                    "Best regards,\nMXtoAI Assistant",
                    "Best regards,",
                    "Warm regards,",
                    "_Feel free to reply to this email to continue our conversation._",
                    "MXtoAI Assistant",
                    "> **Disclaimer:**",
                ]
                temp_content = email_body_content_source
                for marker in signature_markers:
                    temp_content = re.sub(
                        r"^[\s\n]*" + re.escape(marker) + r".*$",
                        "",
                        temp_content,
                        flags=re.IGNORECASE | re.MULTILINE,
                    ).strip()

                email_text_content = self.report_formatter.format_report(
                    temp_content, format_type="text", include_signature=True
                )
                email_html_content = self.report_formatter.format_report(
                    temp_content, format_type="html", include_signature=True
                )
            else:
                fallback_msg = (
                    "I apologize, but I encountered an issue generating the detailed response. "
                    "Please try again later or contact support if this issue persists."
                )
                email_text_content = self.report_formatter.format_report(
                    fallback_msg, format_type="text", include_signature=True
                )
                email_html_content = self.report_formatter.format_report(
                    fallback_msg, format_type="html", include_signature=True
                )
                errors_list.append(ProcessingError(message="No final answer text was generated or extracted"))
                email_sent_status.status = "error"
                email_sent_status.error = "No reply text was generated"

            return DetailedEmailProcessingResult(
                metadata=ProcessingMetadata(
                    processed_at=processed_at_time,
                    mode=current_email_handle,
                    errors=errors_list,
                    email_sent=email_sent_status,
                ),
                email_content=EmailContentDetails(
                    text=email_text_content,
                    html=email_html_content,
                    enhanced={"text": email_text_content, "html": email_html_content},
                ),
                attachments=AttachmentsProcessingResult(
                    summary=attachment_proc_summary, processed=processed_attachment_details
                ),
                calendar_data=calendar_result_data,
                research=AgentResearchOutput(
                    findings_content=research_output_findings, metadata=research_output_metadata
                )
                if research_output_findings or research_output_metadata
                else None,
            )

        except Exception as e: # pylint: disable=broad-except
            logger.exception(f"Critical error in _process_agent_result: {e!s}")
            if not errors_list:
                errors_list.append(ProcessingError(message="Critical error in _process_agent_result", details=str(e)))

            current_timestamp = datetime.now().isoformat()
            if email_sent_status.status != "error":
                email_sent_status.status = "error"
                email_sent_status.error = f"Critical error in _process_agent_result: {e!s}"
                email_sent_status.timestamp = current_timestamp

            fb_text = "I encountered a critical error processing your request during result generation."
            final_email_text = email_text_content or self.report_formatter.format_report(
                fb_text, format_type="text", include_signature=True
            )
            final_email_html = email_html_content or self.report_formatter.format_report(
                fb_text, format_type="html", include_signature=True
            )

            return DetailedEmailProcessingResult(
                metadata=ProcessingMetadata(
                    processed_at=processed_at_time,
                    mode=current_email_handle,
                    errors=errors_list,
                    email_sent=email_sent_status,
                ),
                email_content=EmailContentDetails(
                    text=final_email_text,
                    html=final_email_html,
                    enhanced={"text": final_email_text, "html": final_email_html},
                ),
                attachments=AttachmentsProcessingResult(
                    summary=attachment_proc_summary,
                    processed=processed_attachment_details,
                ),
                calendar_data=calendar_result_data,
                research=AgentResearchOutput(
                    findings_content=research_output_findings, metadata=research_output_metadata
                )
                if research_output_findings or research_output_metadata
                else None,
            )

    def process_email(
        self,
        email_request: EmailRequest,
        email_instructions: ProcessingInstructions,
    ) -> DetailedEmailProcessingResult:
        """
        Process an email using the agent based on the provided email handle instructions.

        Args:
            email_request: EmailRequest instance containing email data.
            email_instructions: ProcessingInstructions object with processing configuration.

        Returns:
            DetailedEmailProcessingResult: Pydantic model with structured processing results.
        """
        try:
            self.routed_model.current_handle = email_instructions
            task = self._create_task(email_request, email_instructions)
            logger.info("Starting agent execution setup...")

            # Get MCP server configurations
            mcp_servers_config = self._get_mcp_servers_config()
            
            all_tools = list(self.base_tools)  # Start with base tools
            agent_steps = []
            final_answer_obj = None
            
            agent_description = (
                "An agent that processes emails, generates summaries, replies, and conducts research "
                "with advanced capabilities including web search, web browsing, code execution, and MCP tools."
            )

            # Load MCP tools using our custom implementation
            if mcp_servers_config:
                try:
                    logger.info(f"Loading MCP tools from {len(mcp_servers_config)} configured servers")
                    
                    with load_mcp_tools_from_config(mcp_servers_config) as mcp_tools:
                        all_tools.extend(mcp_tools)
                        mcp_tools_count = len(mcp_tools)
                        
                        logger.info(f"Successfully loaded {mcp_tools_count} MCP tools")
                        logger.info(f"Total tools available: {len(all_tools)} (Base: {len(self.base_tools)}, MCP: {mcp_tools_count})")
                        
                        # Initialize ToolCallingAgent with all tools
                        agent = ToolCallingAgent(
                            model=self.routed_model,
                            tools=all_tools,
                            max_steps=12,
                            verbosity_level=2,
                            planning_interval=4,
                            name="email_processing_agent_with_mcp",
                            description=agent_description,
                            provide_run_summary=True,
                        )
                        logger.debug("Initialized ToolCallingAgent with MCP tools")

                        logger.info("Starting agent.run() with MCP tools...")
                        final_answer_obj = agent.run(task)
                        logger.info("Agent.run() execution completed.")

                        agent_steps = list(agent.memory.steps)
                        logger.debug(f"Captured {len(agent_steps)} steps from agent memory.")
                        
                except Exception as e:
                    logger.error(f"Failed to load MCP tools, falling back to base tools only: {e}")
                    # Fall back to base tools only
                    agent = ToolCallingAgent(
                        model=self.routed_model,
                        tools=all_tools,  # Just base tools at this point
                        max_steps=12,
                        verbosity_level=2,
                        planning_interval=4,
                        name="email_processing_agent_base_only",
                        description=agent_description,
                        provide_run_summary=True,
                    )
                    logger.info("Starting agent.run() with base tools only...")
                    final_answer_obj = agent.run(task)
                    agent_steps = list(agent.memory.steps)
            else:
                # No MCP servers configured, use base tools only
                logger.info("No MCP servers configured, using base tools only")
                agent = ToolCallingAgent(
                    model=self.routed_model,
                    tools=all_tools,
                    max_steps=12,
                    verbosity_level=2,
                    planning_interval=4,
                    name="email_processing_agent_base_only",
                    description=agent_description,
                    provide_run_summary=True,
                )
                logger.info("Starting agent.run() with base tools only...")
                final_answer_obj = agent.run(task)
                agent_steps = list(agent.memory.steps)

            # Process the results
            processed_result = self._process_agent_result(final_answer_obj, agent_steps, email_instructions.handle)

            if not processed_result.email_content or not processed_result.email_content.text:
                msg = "No reply text was generated by _process_agent_result"
                logger.error(msg)
                processed_result.metadata.errors.append(ProcessingError(message=msg))
                processed_result.metadata.email_sent.status = "error"
                processed_result.metadata.email_sent.error = msg
                logger.info(f"Email processed (but no reply text generated) with handle: {email_instructions.handle}")
                return processed_result

            logger.info(f"Email processed successfully with handle: {email_instructions.handle}")
            return processed_result

        except Exception as e:  # pylint: disable=broad-except
            error_msg = f"Critical error in email processing: {e!s}"
            logger.error(error_msg, exc_info=True)

            now_iso = datetime.now().isoformat()
            error_email_text = self.report_formatter.format_report(
                "I encountered a critical error processing your request.",
                format_type="text",
                include_signature=True,
            )
            error_email_html = self.report_formatter.format_report(
                "I encountered a critical error processing your request.",
                format_type="html",
                include_signature=True,
            )
            return DetailedEmailProcessingResult(
                metadata=ProcessingMetadata(
                    processed_at=now_iso,
                    mode=email_instructions.handle if email_instructions else "unknown",
                    errors=[ProcessingError(message=error_msg, details=str(e))],
                    email_sent=EmailSentStatus(status="error", error=error_msg, timestamp=now_iso),
                ),
                email_content=EmailContentDetails(
                    text=error_email_text,
                    html=error_email_html,
                    enhanced={"text": error_email_text, "html": error_email_html},
                ),
                attachments=AttachmentsProcessingResult(processed=[]),
                calendar_data=None,
                research=None,
            )
