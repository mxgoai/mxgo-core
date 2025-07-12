import ast
import json
import re
from datetime import datetime, timezone
from typing import Any, Union

from dotenv import load_dotenv

# Update imports to use proper classes from smolagents
from smolagents import Tool, ToolCallingAgent

# Import the base agent class
from mxtoai.agents.agent import BaseAgent

# Add imports for the new default tools
from mxtoai._logging import get_logger, get_smolagents_console
from mxtoai.config import SCHEDULED_TASKS_MAX_PER_EMAIL
from mxtoai.crud import count_active_tasks_for_user
from mxtoai.db import init_db_connection
from mxtoai.prompts.base_prompts import (
    MARKDOWN_STYLE_GUIDE,
    RESEARCH_GUIDELINES,
    RESPONSE_GUIDELINES,
    SECURITY_GUIDELINES,
)
from mxtoai.prompts.template_prompts import (
    SCHEDULED_TASK_DISTILLED_INSTRUCTIONS_TEMPLATE,
)
from mxtoai.request_context import RequestContext
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
    PDFExportResult,
    ProcessedAttachmentDetail,
    ProcessingError,
    ProcessingInstructions,
    ProcessingMetadata,
    ToolName,
)

# Import citation management and web search tools
from mxtoai.tools import create_tool_mapping
from mxtoai.tools.scheduled_tasks_tool import ScheduledTasksTool

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


class EmailAgent(BaseAgent):
    """
    Email processing agent that can summarize, reply to, and research information for emails.
    """

    def __init__(
        self,
        email_request: EmailRequest,
        processing_instructions: ProcessingInstructions,
        attachment_dir: str = "email_attachments",
        *,
        verbose: bool = False,
        attachment_info: list[dict] | None = None,
    ):
        """
        Initialize the email agent with tools for different operations.

        Args:
            email_request: The email request to process
            processing_instructions: Instructions defining which tools are allowed
            attachment_dir: Directory to store email attachments
            verbose: Whether to enable verbose logging
            attachment_info: Optional list of attachment info to load into memory

        """
        # Initialize base class
        super().__init__(
            email_request=email_request,
            processing_instructions=processing_instructions,
            attachment_dir=attachment_dir,
            verbose=verbose,
            attachment_info=attachment_info,
        )

        # Initialize tools based on allowed_tools from processing instructions
        self.available_tools = self._initialize_allowed_tools()

        logger.info(f"Agent tools initialized: {[tool.name for tool in self.available_tools]}")
        self._init_agent()
        logger.info("Email agent initialized successfully")

    def _init_agent(self):
        """Initialize the smolagents ToolCallingAgent."""
        # Initialize the routed model with the default model group
        self.routed_model = RoutedLiteLLMModel()

        # Create agent
        self.agent = ToolCallingAgent(
            model=self.routed_model,
            tools=self.available_tools,
            max_steps=12,
            verbosity_level=2,  # Increased back to 2 to capture detailed Rich console output
            planning_interval=4,
            name="mxtoai_email_processing_agent",
            description="I'm MXtoAI agent - an intelligent email processing agent that automates email-driven tasks and workflows. I can analyze emails, generate professional summaries and replies, conduct comprehensive research using web search and external APIs, process attachments (documents, images, PDFs), extract and create calendar events, export content to PDF, and execute code for data analysis. I maintain professional communication standards while providing accurate, well-researched responses tailored to your specific email handling requirements.",
            provide_run_summary=True,
        )

        # Set up integrated Rich console that feeds into loguru/logfire pipeline
        # This captures smolagents verbose output and integrates it with our unified logging
        smolagents_console = get_smolagents_console()

        # Override agent's console with our loguru-integrated console
        if hasattr(self.agent, "logger") and hasattr(self.agent.logger, "console"):
            self.agent.logger.console = smolagents_console
        if (
            hasattr(self.agent, "monitor")
            and hasattr(self.agent.monitor, "logger")
            and hasattr(self.agent.monitor.logger, "console")
        ):
            self.agent.monitor.logger.console = smolagents_console

        logger.debug("Agent initialized with routed model configuration, loguru-integrated Rich console")

    def _initialize_allowed_tools(self) -> list[Tool]:
        """
        Initialize tools based on the allowed_tools field from processing instructions.

        Returns:
            list[Tool]: List of allowed tools for this handle

        """
        # Get allowed tools from processing instructions
        allowed_tools = self.processing_instructions.allowed_tools

        # If no allowed_tools specified, use all tools (backward compatibility)
        if allowed_tools is None:
            logger.warning("No allowed_tools specified in processing instructions, using all tools")
            return self._initialize_all_tools()

        # Create mapping of tool names to tool instances
        tool_mapping = create_tool_mapping(
            context=self.context,
            scheduled_tasks_tool_factory=self._create_limited_scheduled_tasks_tool,
            allowed_python_imports=ALLOWED_PYTHON_IMPORTS,
        )

        # Filter tools based on allowed list
        filtered_tools = []
        for tool_name in allowed_tools:
            if tool_name in tool_mapping:
                tool_instance = tool_mapping[tool_name]
                if tool_instance is not None:  # Handle tools that might not be available (e.g., missing API keys)
                    filtered_tools.append(tool_instance)
                    logger.debug(f"Added allowed tool: {tool_name.value}")
                else:
                    logger.warning(
                        f"Tool {tool_name.value} is in allowed list but not available (missing dependencies/API keys)"
                    )
                    # Log specific reasons for common tools
                    if tool_name == ToolName.BRAVE_SEARCH:
                        logger.debug("BRAVE_SEARCH_API_KEY not found")
                    elif tool_name == ToolName.GOOGLE_SEARCH:
                        logger.debug("SERPAPI_API_KEY or SERPER_API_KEY not found")
                    elif tool_name in [ToolName.LINKEDIN_FRESH_DATA, ToolName.LINKEDIN_DATA_API]:
                        logger.debug("RAPIDAPI_KEY not found or LinkedIn tool initialization failed")
            else:
                logger.warning(f"Unknown tool in allowed list: {tool_name.value}")

        logger.info(
            f"Initialized {len(filtered_tools)} allowed tools for handle '{self.processing_instructions.handle}': {[tool.name for tool in filtered_tools]}"
        )
        return filtered_tools

    def _initialize_all_tools(self) -> list[Tool]:
        """
        Initialize all available tools (backward compatibility method).

        Returns:
            list[Tool]: List of all available tools

        """
        # Use centralized tool mapping for consistency
        tool_mapping = create_tool_mapping(
            context=self.context,
            scheduled_tasks_tool_factory=self._create_limited_scheduled_tasks_tool,
            allowed_python_imports=ALLOWED_PYTHON_IMPORTS,
        )

        # Get all available tools (non-None values)
        all_tools = [tool for tool in tool_mapping.values() if tool is not None]

        logger.info(f"Initialized {len(all_tools)} tools for backward compatibility mode")
        return all_tools

    def _get_required_actions(self, mode: str) -> list[str]:
        """
        Get list of required actions based on mode.

        Args:
            mode: The mode of operation (e.g., "summary", "reply", "research", "full")

        Returns:
            List[str]: List of actions to be performed by the agent

        """
        actions = []
        if mode in ["summary", "full"]:
            actions.append("Generate summary")
        if mode in ["reply", "full"]:
            actions.append("Generate reply")
        if mode in ["research", "full"]:
            actions.append("Conduct research")
        return actions

    def _create_attachment_task(self, attachment_details: list[str]) -> str:
        """
        Return instructions for processing attachments, if any.

        Args:
            attachment_details: List of formatted attachment details

        Returns:
            str: Instructions for processing attachments

        """
        return f"Process these attachments:\n{chr(10).join(attachment_details)}" if attachment_details else ""

    def _create_task(self, email_request: EmailRequest, email_instructions: ProcessingInstructions) -> str:
        """
        Create a task description for the agent based on email handle instructions.

        Args:
            email_request: EmailRequest instance containing email data
            email_instructions: EmailHandleInstructions object containing processing configuration

        Returns:
            str: The task description for the agent

        """
        # process attachments if specified
        attachments = (
            self._format_attachments(email_request.attachments)
            if email_instructions.process_attachments and email_request.attachments
            else []
        )

        output_template = email_instructions.output_template

        return self._create_task_template(
            handle=email_instructions.handle,
            email_context=self._create_email_context(email_request, attachments),
            handle_specific_template=email_instructions.task_template,
            attachment_task=self._create_attachment_task(attachments),
            output_template=output_template,
            distilled_processing_instructions=email_request.distilled_processing_instructions,
        )

    def _format_attachments(self, attachments: list[EmailAttachment]) -> list[str]:
        """
        Format attachment details for inclusion in the task.

        Args:
            attachments: List of EmailAttachment objects

        Returns:
            List[str]: Formatted attachment details

        """
        return [
            f'- {att.filename} (Type: {att.contentType}, Size: {att.size} bytes)\n  EXACT FILE PATH: "{att.path}"'
            for att in attachments
        ]

    def _create_task_template(
        self,
        handle: str,
        email_context: str,
        handle_specific_template: str = "",
        attachment_task: str = "",
        *,
        output_template: str = "",
        distilled_processing_instructions: str | None = None,
    ) -> str:
        """
        Combine all task components into the final task description.

        Args:
            handle: The email handle being processed.
            email_context: The context information extracted from the email.
            handle_specific_template: Any specific template for the handle.
            attachment_task: Instructions for processing attachments.
            output_template: The output template to use.
            distilled_processing_instructions: Specific processing instructions for scheduled tasks.

        Returns:
            str: The complete task description for the agent.

        """
        # Create distilled processing instructions section for scheduled tasks
        distilled_section = (
            SCHEDULED_TASK_DISTILLED_INSTRUCTIONS_TEMPLATE.format(
                distilled_processing_instructions=distilled_processing_instructions
            )
            if distilled_processing_instructions
            else ""
        )

        # Merge the task components into a single string by listing the sections
        sections = [
            f"Process this email according to the '{handle}' instruction type.\n",
            email_context,
            distilled_section,
            RESEARCH_GUIDELINES["optional"],
            attachment_task,
            handle_specific_template,
            output_template,
            RESPONSE_GUIDELINES,
            MARKDOWN_STYLE_GUIDE,
            SECURITY_GUIDELINES,
        ]

        return "\n\n".join(filter(None, sections))

    def _process_agent_result(  # noqa: PLR0912, PLR0915
        self, final_answer_obj: Any, agent_steps: list, current_email_handle: str
    ) -> DetailedEmailProcessingResult:
        processed_at_time = datetime.now(timezone.utc).isoformat()

        # Initialize schema components
        errors_list: list[ProcessingError] = []
        email_sent_status = EmailSentStatus(status="pending", timestamp=processed_at_time)

        attachment_proc_summary: Union[str, None] = None
        processed_attachment_details: list[ProcessedAttachmentDetail] = []

        calendar_result_data: Union[CalendarResult, None] = None

        research_output_findings: Union[str, None] = None
        research_output_metadata: Union[AgentResearchMetadata, None] = None

        pdf_export_result: Union[PDFExportResult, None] = None

        final_answer_from_llm: Union[str, None] = None
        email_text_content: Union[str, None] = None
        email_html_content: Union[str, None] = None

        try:
            logger.debug(f"Processing final answer object type: {type(final_answer_obj)}")
            logger.debug(f"Processing {len(agent_steps)} agent step entries.")

            for i, step in enumerate(agent_steps):
                logger.debug(f"[Memory Step {i + 1}] Type: {type(step)}")

                tool_name = None
                tool_output = None

                if hasattr(step, "tool_calls") and isinstance(step.tool_calls, list) and len(step.tool_calls) > 0:
                    first_tool_call = step.tool_calls[0]
                    tool_name = getattr(first_tool_call, "name", None)
                    if not tool_name:
                        logger.warning(f"[Memory Step {i + 1}] Could not extract tool name from first call.")
                        tool_name = None

                    action_out = getattr(step, "action_output", None)
                    obs_out = getattr(step, "observations", None)
                    tool_output = action_out if action_out is not None else obs_out

                if tool_name and tool_output is not None:
                    needs_parsing = tool_name in [
                        "meeting_creator",
                        "attachment_processor",
                        "pdf_export",
                        "scheduled_tasks",
                    ]
                    if isinstance(tool_output, str) and needs_parsing:
                        try:
                            # Try JSON parsing first for tools that return ToolOutputWithCitations
                            if tool_name in ["attachment_processor"]:
                                tool_output = json.loads(tool_output)
                            else:
                                tool_output = ast.literal_eval(tool_output)
                        except (ValueError, SyntaxError, json.JSONDecodeError) as e:
                            logger.error(
                                f"[Memory Step {i + 1}] Failed to parse '{tool_name}' output: {e!s}. Content: {tool_output[:200]}..."
                            )
                            errors_list.append(
                                ProcessingError(message=f"Failed to parse {tool_name} output", details=str(e))
                            )
                            continue
                        except Exception as e:
                            logger.error(
                                f"[Memory Step {i + 1}] Unexpected error parsing '{tool_name}' output: {e!s}. Content: {tool_output[:200]}..."
                            )
                            errors_list.append(
                                ProcessingError(message=f"Unexpected error parsing {tool_name} output", details=str(e))
                            )
                            continue

                    logger.debug(
                        f"[Memory Step {i + 1}] Processing tool call: '{tool_name}', Output Type: '{type(tool_output)}'"
                    )

                    if tool_name == "attachment_processor" and isinstance(tool_output, dict):
                        # Handle new ToolOutputWithCitations format
                        if "metadata" in tool_output and "attachments" in tool_output["metadata"]:
                            attachment_proc_summary = tool_output.get("content")  # Summary is now in content field
                            for attachment_data in tool_output["metadata"]["attachments"]:
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
                                if (
                                    "content" in attachment_data
                                    and isinstance(attachment_data["content"], dict)
                                    and attachment_data["content"].get("caption")
                                ):
                                    pa_detail.caption = attachment_data["content"]["caption"]
                                processed_attachment_details.append(pa_detail)
                        else:
                            # Handle legacy format (fallback)
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
                                if (
                                    "content" in attachment_data
                                    and isinstance(attachment_data["content"], dict)
                                    and attachment_data["content"].get("caption")
                                ):
                                    pa_detail.caption = attachment_data["content"]["caption"]
                                processed_attachment_details.append(pa_detail)

                    elif tool_name == "meeting_creator" and isinstance(tool_output, dict):
                        if tool_output.get("status") == "success" and tool_output.get("ics_content"):
                            calendar_result_data = CalendarResult(ics_content=tool_output["ics_content"])
                        else:
                            error_msg = tool_output.get("message", "Schedule generator failed or missing ICS content.")
                            errors_list.append(ProcessingError(message="Schedule Tool Error", details=error_msg))

                    elif tool_name == "pdf_export" and isinstance(tool_output, dict):
                        if tool_output.get("success"):
                            pdf_export_result = PDFExportResult(
                                filename=tool_output.get("filename", "document.pdf"),
                                file_path=tool_output.get("file_path", ""),
                                file_size=tool_output.get("file_size", 0),
                                title=tool_output.get("title", "Document"),
                                pages_estimated=tool_output.get("pages_estimated", 1),
                                mimetype=tool_output.get("mimetype", "application/pdf"),
                                temp_dir=tool_output.get("temp_dir"),
                            )
                            logger.info(f"PDF export successful: {pdf_export_result.filename}")
                        else:
                            error_msg = tool_output.get("error", "PDF export failed")
                            details = tool_output.get("details", "")
                            errors_list.append(
                                ProcessingError(message="PDF Export Error", details=f"{error_msg}. {details}")
                            )
                            logger.error(f"PDF export failed: {error_msg}")

                    elif tool_name == "scheduled_tasks" and isinstance(tool_output, dict):
                        if tool_output.get("success") and tool_output.get("task_id"):
                            logger.info(f"Scheduled task created successfully with ID: {tool_output['task_id']}")
                        else:
                            error_msg = tool_output.get("message", "Scheduled task creation failed")
                            error_type = (
                                "Scheduled Task Limit Exceeded"
                                if tool_output.get("error") == "Task limit exceeded"
                                else "Scheduled Task Error"
                            )
                            errors_list.append(ProcessingError(message=error_type, details=error_msg))
                            if tool_output.get("error") == "Task limit exceeded":
                                logger.warning(f"Scheduled task limit exceeded: {error_msg}")
                            else:
                                logger.error(f"Scheduled task creation failed: {error_msg}")

                    else:
                        logger.debug(
                            f"[Memory Step {i + 1}] Tool '{tool_name}' output processed (no specific handler). Output: {str(tool_output)[:200]}..."
                        )
                else:
                    logger.debug(
                        f"[Memory Step {i + 1}] Skipping step (Type: {type(step)}), not a relevant ActionStep or missing output."
                    )

            # Extract final answer from LLM
            if hasattr(final_answer_obj, "text"):
                final_answer_from_llm = str(final_answer_obj.text).strip()
                logger.debug("Extracted final answer from AgentResponse.text")
            elif isinstance(final_answer_obj, str):
                final_answer_from_llm = final_answer_obj.strip()
                logger.debug("Extracted final answer from string")
            elif hasattr(final_answer_obj, "_value"):  # Check for older AgentText structure
                final_answer_from_llm = str(final_answer_obj._value).strip()  # noqa: SLF001
                logger.debug("Extracted final answer from AgentText._value")
            elif hasattr(final_answer_obj, "answer"):  # Handle final_answer tool call argument
                # Check if the argument itself is the content string
                if isinstance(getattr(final_answer_obj, "answer", None), str):
                    final_answer_from_llm = str(final_answer_obj.answer).strip()
                    logger.debug("Extracted final answer from final_answer tool argument string")
                # Or if it's nested in arguments (less likely for final_answer but check)
                elif (
                    isinstance(getattr(final_answer_obj, "arguments", None), dict)
                    and "answer" in final_answer_obj.arguments
                ):
                    final_answer_from_llm = str(final_answer_obj.arguments["answer"]).strip()
                    logger.debug("Extracted final answer from final_answer tool arguments dict")
                else:
                    final_answer_from_llm = str(final_answer_obj).strip()
                    logger.warning(
                        f"Could not find specific answer attribute in final_answer object, using str(). Result: {final_answer_from_llm[:100]}..."
                    )
            else:
                final_answer_from_llm = str(final_answer_obj).strip()
                logger.warning(
                    f"Could not find specific answer attribute in final_answer object, using str(). Result: {final_answer_from_llm[:100]}..."
                )

            # Determine email body content
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
                        r"^[\s\n]*" + re.escape(marker) + r".*$", "", temp_content, flags=re.IGNORECASE | re.MULTILINE
                    ).strip()

                # Finalize content with citations if any were collected
                temp_content = self._finalize_response_with_citations(temp_content)

                email_text_content = self.report_formatter.format_report(
                    temp_content, format_type="text", include_signature=True
                )
                email_html_content = self.report_formatter.format_report(
                    temp_content, format_type="html", include_signature=True
                )
            else:
                fallback_msg = "I apologize, but I encountered an issue generating the detailed response. Please try again later or contact support if this issue persists."
                email_text_content = self.report_formatter.format_report(
                    fallback_msg, format_type="text", include_signature=True
                )
                email_html_content = self.report_formatter.format_report(
                    fallback_msg, format_type="html", include_signature=True
                )
                errors_list.append(ProcessingError(message="No final answer text was generated or extracted"))
                email_sent_status.status = "error"
                email_sent_status.error = "No reply text was generated"

            # Construct the final Pydantic model INSIDE the try block
            return DetailedEmailProcessingResult(
                metadata=ProcessingMetadata(
                    processed_at=processed_at_time,
                    mode=current_email_handle,  # Use the passed handle for mode
                    errors=errors_list,
                    email_sent=email_sent_status,
                ),
                email_content=EmailContentDetails(
                    text=email_text_content,
                    html=email_html_content,
                    # Assuming enhanced content is same as base for now
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
                pdf_export=pdf_export_result,
            )

        except Exception as e:
            logger.exception("Critical error in _process_agent_result")
            # Ensure errors_list and email_sent_status are updated
            # If these were initialized outside and before this try-except, they might already exist.
            # Re-initialize or ensure they are correctly formed for the error state.
            # This part already handles populating errors_list and setting email_sent_status.

            # Ensure basic structure for fallback if critical error happened early
            if not errors_list:  # If the error happened before any specific error was added
                errors_list.append(ProcessingError(message="Critical error in _process_agent_result", details=str(e)))

            current_timestamp = datetime.now(timezone.utc).isoformat()  # Use a fresh timestamp
            if email_sent_status.status != "error":  # If not already set to error by prior logic
                email_sent_status.status = "error"
                email_sent_status.error = f"Critical error in _process_agent_result: {e!s}"
                email_sent_status.timestamp = current_timestamp

            # Fallback email content if not already set
            fb_text = "I encountered a critical error processing your request during result generation."
            final_email_text = (
                email_text_content
                if email_text_content
                else self.report_formatter.format_report(fb_text, format_type="text", include_signature=True)
            )
            final_email_html = (
                email_html_content
                if email_html_content
                else self.report_formatter.format_report(fb_text, format_type="html", include_signature=True)
            )

            # Construct and return an error-state DetailedEmailProcessingResult
            return DetailedEmailProcessingResult(
                metadata=ProcessingMetadata(
                    processed_at=processed_at_time,  # or current_timestamp, consider consistency
                    mode=current_email_handle,
                    errors=errors_list,
                    email_sent=email_sent_status,
                ),
                email_content=EmailContentDetails(
                    text=final_email_text,
                    html=final_email_html,
                    enhanced={"text": final_email_text, "html": final_email_html},  # ensure enhanced also has fallback
                ),
                attachments=AttachmentsProcessingResult(
                    summary=attachment_proc_summary
                    if attachment_proc_summary
                    else None,  # Keep any partial data if available
                    processed=processed_attachment_details if processed_attachment_details else [],
                ),
                calendar_data=calendar_result_data,  # Keep any partial data
                research=AgentResearchOutput(  # Keep any partial data
                    findings_content=research_output_findings, metadata=research_output_metadata
                )
                if research_output_findings or research_output_metadata
                else None,
                pdf_export=pdf_export_result,
            )

    def process_email(
        self,
        email_request: EmailRequest,
        email_instructions: ProcessingInstructions,
    ) -> DetailedEmailProcessingResult:  # Updated return type annotation
        """
        Process an email using the agent based on the provided email handle instructions.

        Args:
            email_request: EmailRequest instance containing email data
            email_instructions: ProcessingInstructions object containing processing configuration

        Returns:
            DetailedEmailProcessingResult: Pydantic model with structured processing results.

        """
        try:
            self.routed_model.current_handle = email_instructions
            task = self._create_task(email_request, email_instructions)

            logger.info("Starting agent execution...")
            final_answer_obj = self.agent.run(task, additional_args={"email_request": email_request})
            logger.info("Agent execution completed.")

            agent_steps = list(self.agent.memory.steps)
            logger.info(f"Captured {len(agent_steps)} steps from agent memory.")

            processed_result = self._process_agent_result(final_answer_obj, agent_steps, email_instructions.handle)

        except Exception as e:
            error_msg = f"Critical error in email processing: {e!s}"
            logger.exception(error_msg)

            # Construct a DetailedEmailProcessingResult for error cases
            now_iso = datetime.now(timezone.utc).isoformat()
            return DetailedEmailProcessingResult(
                metadata=ProcessingMetadata(
                    processed_at=now_iso,
                    mode=email_instructions.handle if email_instructions else "unknown",
                    errors=[ProcessingError(message=error_msg, details=str(e))],
                    email_sent=EmailSentStatus(status="error", error=error_msg, timestamp=now_iso),
                ),
                email_content=EmailContentDetails(
                    text=self.report_formatter.format_report(
                        "I encountered a critical error processing your request.",
                        format_type="text",
                        include_signature=True,
                    ),
                    html=self.report_formatter.format_report(
                        "I encountered a critical error processing your request.",
                        format_type="html",
                        include_signature=True,
                    ),
                    enhanced={"text": None, "html": None},
                ),
                attachments=AttachmentsProcessingResult(processed=[]),
                calendar_data=None,
                research=None,
                pdf_export=None,
            )
        else:
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

    def _create_limited_scheduled_tasks_tool(self) -> Tool:
        """
        Create a scheduled tasks tool with a call limit wrapper.

        Returns:
            Tool: Wrapped scheduled tasks tool with call limiting

        """
        # Create the base tool
        base_tool = ScheduledTasksTool(context=self.context)

        max_calls = SCHEDULED_TASKS_MAX_PER_EMAIL

        # Store original forward method
        original_forward = base_tool.forward

        def limited_forward(*args, **kwargs):
            """Wrapper that limits scheduled task calls to 5 per email."""
            # Check current active task count for this user from database
            db_connection = init_db_connection()
            with db_connection.get_session() as session:
                user_email = self.context.email_request.from_email

                # Count only active (non-terminal) tasks using CRUD
                current_active_count = count_active_tasks_for_user(session, user_email)

                if current_active_count >= max_calls:
                    logger.warning(
                        f"Scheduled task limit reached ({max_calls} active tasks per email). User has {current_active_count} active tasks."
                    )
                    return {
                        "success": False,
                        "error": "Task limit exceeded",
                        "message": f"Maximum of {max_calls} scheduled tasks allowed per email. You currently have {current_active_count} active tasks. Delete some tasks to create new ones.",
                        "active_tasks": current_active_count,
                        "max_allowed": max_calls,
                    }

            # If we're under the limit, proceed with task creation
            logger.info(f"Creating scheduled task (user has {current_active_count}/{max_calls} active tasks)")

            # Call the original method
            return original_forward(*args, **kwargs)

        # Replace the forward method
        base_tool.forward = limited_forward

        return base_tool


