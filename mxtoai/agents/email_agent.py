import ast
import os
import re
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

# Update imports to use proper classes from smolagents
from smolagents import Tool, ToolCallingAgent

# Add imports for the new default tools
from smolagents.default_tools import (
    DuckDuckGoSearchTool,
    GoogleSearchTool,
    PythonInterpreterTool,
    VisitWebpageTool,
)

from mxtoai._logging import get_logger
from mxtoai.prompts.base_prompts import create_attachment_processing_task, create_email_context, create_task_template
from mxtoai.routed_litellm_model import RoutedLiteLLMModel
from mxtoai.schemas import EmailRequest
from mxtoai.scripts.report_formatter import ReportFormatter
from mxtoai.scripts.visual_qa import azure_visualizer
from mxtoai.tools.attachment_processing_tool import AttachmentProcessingTool
from mxtoai.tools.deep_research_tool import DeepResearchTool

# Import the new fallback search tool
from mxtoai.tools.fallback_search_tool import FallbackWebSearchTool
from mxtoai.tools.schedule_tool import ScheduleTool

# Load environment variables
load_dotenv(override=True)

# Configure logger
logger = get_logger("email_agent")

# Custom role conversions for the model
custom_role_conversions = {"tool-call": "assistant", "tool-response": "user"}

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
    # Add any other safe standard library modules needed
]


class EmailAgent:
    """
    Email processing agent that can summarize, reply to, and research information for emails.
    """

    def __init__(
        self, attachment_dir: str = "email_attachments", verbose: bool = False, enable_deep_research: bool = False
    ):
        """
        Initialize the email agent with tools for different operations.

        Args:
            attachment_dir: Directory to store email attachments
            verbose: Whether to enable verbose logging
            enable_deep_research: Whether to enable Jina AI deep research functionality (uses API tokens)

        """
        # Set up logging
        if verbose:
            # logger.setLevel(logging.DEBUG) # Removed: Logger object may not support setLevel directly
            # Consider configuring logging level via environment variables or central logging setup
            logger.debug("Verbose logging enabled via __init__ flag (actual level depends on logger config).")

        # Create attachment directory
        self.attachment_dir = attachment_dir
        os.makedirs(self.attachment_dir, exist_ok=True)

        # Instantiate tools
        self.attachment_tool = AttachmentProcessingTool()
        self.report_formatter = ReportFormatter()  # Used elsewhere, keep initialization
        self.schedule_tool = ScheduleTool()
        self.visit_webpage_tool = VisitWebpageTool()
        # Instantiate PythonInterpreterTool with allowed imports
        self.python_tool = PythonInterpreterTool(authorized_imports=ALLOWED_PYTHON_IMPORTS)

        # Initialize search tools with fallback logic
        ddg_search_tool = DuckDuckGoSearchTool()
        google_search_tool = None
        if os.getenv("SERPAPI_API_KEY"):
            try:
                google_search_tool = GoogleSearchTool(provider="serpapi")
                logger.info("Initialized GoogleSearchTool with SerpAPI.")
            except ValueError as e:
                logger.warning(f"Failed to initialize GoogleSearchTool with SerpAPI: {e}")
        elif os.getenv("SERPER_API_KEY"):
            try:
                google_search_tool = GoogleSearchTool(provider="serper")
                logger.info("Initialized GoogleSearchTool with Serper.")
            except ValueError as e:
                logger.warning(f"Failed to initialize GoogleSearchTool with Serper: {e}")
        else:
            logger.warning(
                "GoogleSearchTool not initialized. Missing SERPAPI_API_KEY or SERPER_API_KEY environment variable."
            )

        self.fallback_search_tool = FallbackWebSearchTool(
            primary_tool=google_search_tool, secondary_tool=ddg_search_tool
        )
        logger.info(
            f"Initialized FallbackWebSearchTool. Primary: {google_search_tool.name if google_search_tool else 'None'}, Secondary: {ddg_search_tool.name}"
        )

        # Initialize deep research tool conditionally
        self.research_tool = None
        if os.getenv("JINA_API_KEY"):
            self.research_tool = DeepResearchTool()
            if enable_deep_research:
                # Assuming DeepResearchTool has an enable_deep_research method or similar setup
                try:
                    # If it needs specific enabling logic, call it here
                    self.research_tool.enable_deep_research()
                    logger.info("Deep research functionality enabled for DeepResearchTool.")
                except AttributeError:
                    logger.warning(
                        "DeepResearchTool does not require explicit enabling or lacks 'enable_deep_research' method."
                    )

        # Define the list of tools available to the agent
        self.available_tools: list[Tool] = [
            self.attachment_tool,
            self.schedule_tool,
            self.visit_webpage_tool,
            self.fallback_search_tool,
            self.python_tool,
            azure_visualizer,
        ]
        if self.research_tool:
            self.available_tools.append(self.research_tool)

        logger.info(f"Agent tools initialized: {[tool.name for tool in self.available_tools]}")

        # Initialize the agent itself (model setup happens here)
        self._init_agent()

        logger.info("Email agent initialized successfully")

    def _init_agent(self):
        """Initialize the ToolCallingAgent with Azure OpenAI."""
        # Initialize the model with routing capabilities
        self.routed_model = RoutedLiteLLMModel()  # Store as instance variable to update handle later

        # Initialize the agent
        self.agent = ToolCallingAgent(
            model=self.routed_model,
            tools=self.available_tools,
            max_steps=12,
            verbosity_level=2,
            planning_interval=4,
            name="email_processing_agent",
            description="An agent that processes emails, generates summaries, replies, and conducts research with advanced capabilities including web search, web browsing, and code execution.",
            provide_run_summary=True,
        )

        logger.debug("Agent initialized with routed model configuration")

    def _get_required_actions(self, mode: str) -> list[str]:
        """Get list of required actions based on mode."""
        actions = []
        if mode in ["summary", "full"]:
            actions.append("Generate summary")
        if mode in ["reply", "full"]:
            actions.append("Generate reply")
        if mode in ["research", "full"]:
            actions.append("Conduct research")
        return actions

    @staticmethod
    def determine_mode_from_email(to_email: str) -> str:
        """
        Determine the processing mode based on the recipient email address.

        Args:
            to_email: The recipient email address

        Returns:
            str: The processing mode ('summary', 'research', 'reply', or 'full' as fallback)

        """
        email_prefix = to_email.split("@")[0].lower()

        mode_mapping = {
            "summarize": "summary",
            "deep": "research",
            "reply": "reply",
            "ask": "full",  # General prompt handle defaults to full processing
        }

        return mode_mapping.get(email_prefix, "full")

    def _get_attachment_types(self, attachments: list[dict[str, Any]]) -> list[str]:
        """Get list of attachment types."""
        types = []
        for att in attachments:
            content_type = att.get("type", "").split("/")[-1].upper()
            if content_type:
                types.append(content_type)
        return types

    def _create_task(self, email_request: EmailRequest, email_instructions: "EmailHandleInstructions") -> str:
        """Create a task description for the agent based on email handle instructions."""
        # Create attachment details with explicit paths if needed
        attachment_details = []
        if email_instructions.process_attachments and email_request.attachments:
            for att in email_request.attachments:
                # Quote the file path to handle spaces correctly
                quoted_path = f'"{att.path}"'
                attachment_details.append(
                    f"- {att.filename} (Type: {att.contentType}, Size: {att.size} bytes)\n"
                    f"  EXACT FILE PATH: {quoted_path}"
                )

        # Create the email context section
        email_context = create_email_context(email_request, attachment_details)

        # Create attachment processing task if needed
        attachment_task = create_attachment_processing_task(attachment_details) if attachment_details else ""

        # Create the complete task template
        return create_task_template(
            handle=email_instructions.handle,
            email_context=email_context,
            handle_specific_template=email_instructions.task_template,
            attachment_task=attachment_task,
            deep_research_mandatory=email_instructions.deep_research_mandatory,
            output_template=email_instructions.output_template
        )

    def _process_agent_result(self, final_answer_obj: Any, agent_steps: list) -> dict[str, Any]:
        """
        Process the agent's result into our expected format, using the agent steps.
        Prioritizes direct output from the 'deep_research' tool if available.

        Args:
            final_answer_obj: The final object returned by agent.run() (likely AgentText)
            agent_steps: The list captured from self.agent.memory.steps after the run

        Returns:
            Dictionary with processing results including email content, calendar data, etc.

        """
        # Initialization
        attachment_summaries = {"text": [], "html": []}
        calendar_data = None
        research_findings_content = None  # Store direct research findings here
        research_metadata = {}  # Store urls etc.
        final_answer_from_llm = None  # Store the LLM's final text answer

        result = {
            "metadata": {
                "processed_at": datetime.now().isoformat(),
                "mode": "unknown",  # Mode might need to be set earlier based on handle
                "errors": [],
                "email_sent": {"status": "pending", "timestamp": datetime.now().isoformat()},
            },
            "email_content": {"html": None, "text": None, "enhanced": {"html": None, "text": None}},
            "attachments": {"summary": None, "processed": []},
            "calendar_data": None,
            "research": None,  # Initialize research key
        }

        try:
            logger.info(f"Processing final answer object type: {type(final_answer_obj)}")
            logger.info(f"Processing {len(agent_steps)} agent step entries.")

            # --- Iterate over agent_steps to extract tool outputs ---
            for i, step in enumerate(agent_steps):
                logger.info(f"[Memory Step {i + 1}] Type: {type(step)}")

                tool_name = None
                tool_output = None

                # Attempt to extract from tool_calls and action_output/observations
                if hasattr(step, "tool_calls") and isinstance(step.tool_calls, list) and len(step.tool_calls) > 0:
                    first_tool_call = step.tool_calls[0]
                    tool_name = getattr(first_tool_call, "name", None)
                    if not tool_name:
                        logger.warning(
                            f"[Memory Step {i + 1}] Found tool_calls, but could not extract name from first call."
                        )
                        tool_name = None  # Reset tool_name if extraction failed

                    # Revised Output Extraction
                    action_out = getattr(step, "action_output", None)
                    obs_out = getattr(step, "observations", None)

                    if action_out is not None:
                        tool_output = action_out
                    elif obs_out is not None:
                        tool_output = obs_out
                    else:
                        tool_output = None
                        logger.warning(
                            f"[Memory Step {i + 1}] Tool call found, but both action_output and observations are None or unavailable."
                        )

                # Proceed only if we successfully extracted tool name and have some output
                if tool_name and tool_output is not None:
                    # Check if tool_output needs parsing
                    needs_parsing = tool_name in ["schedule_generator", "attachment_processor", "deep_research"]

                    if isinstance(tool_output, str) and needs_parsing:
                        try:
                            tool_output = ast.literal_eval(tool_output)
                        except (ValueError, SyntaxError) as e:
                            logger.error(
                                f"[Memory Step {i + 1}] Failed to parse tool_output string ('{tool_name}') using ast.literal_eval. Error: {e!s}. Content: {tool_output[:200]}..."
                            )
                            continue
                        except Exception as e:
                            logger.error(
                                f"[Memory Step {i + 1}] Unexpected error parsing tool_output string ('{tool_name}') using ast.literal_eval. Error: {e!s}. Content: {tool_output[:200]}..."
                            )
                            continue

                    logger.info(
                        f"[Memory Step {i + 1}] Processing tool call: '{tool_name}', Output Type: '{type(tool_output)}'"
                    )

                    # --- Check for schedule_generator output by STRUCTURE ---
                    is_schedule_output = (
                        isinstance(tool_output, dict)
                        and "status" in tool_output
                        and "ics_content" in tool_output
                        and "calendar_links" in tool_output
                    )

                    # --- Process known tools ---
                    if tool_name == "attachment_processor":
                        logger.info(f"[Memory Step {i + 1}] Matched tool: attachment_processor")
                        try:
                            if isinstance(tool_output, dict):
                                result["attachments"]["summary"] = tool_output.get("summary")
                                for attachment in tool_output.get("attachments", []):
                                    sanitized_att = {
                                        "filename": attachment.get("filename", ""),
                                        "size": attachment.get("size", 0),
                                        "type": attachment.get("type", "unknown"),
                                    }
                                    if "error" in attachment:
                                        sanitized_att["error"] = attachment["error"]
                                        result["metadata"]["errors"].append(
                                            f"Error processing {sanitized_att['filename']}: {attachment['error']}"
                                        )
                                        continue
                                    if "content" in attachment:
                                        content = attachment["content"]
                                        if isinstance(content, dict):
                                            if content.get("text"):
                                                text = str(content["text"])
                                                if len(text) > 500:
                                                    text = text[:497] + "..."
                                                attachment_summaries["text"].append(
                                                    f"\\n\\nSummary of {sanitized_att['filename']}\\n{text}"
                                                )
                                                attachment_summaries["html"].append(
                                                    f"<h3>Summary of {sanitized_att['filename']}</h3><p>{text}</p>"
                                                )
                                            elif content.get("caption"):
                                                sanitized_att["caption"] = content["caption"]
                                                attachment_summaries["text"].append(
                                                    f"\\n\\nDescription of {sanitized_att['filename']}\\n{content['caption']}"
                                                )
                                                attachment_summaries["html"].append(
                                                    f"<h3>Description of {sanitized_att['filename']}</h3><p>{content['caption']}</p>"
                                                )
                                    result["attachments"]["processed"].append(sanitized_att)
                        except Exception as e:
                            error_msg = f"Error processing attachment results: {e!s}"
                            logger.error(error_msg)
                            result["metadata"]["errors"].append(error_msg)

                    elif tool_name == "deep_research":
                        logger.info(f"[Memory Step {i + 1}] Matched tool: deep_research")
                        try:
                            if isinstance(tool_output, dict):
                                # Store the primary findings content
                                research_findings_content = tool_output.get("findings", "")
                                # Store metadata separately
                                research_metadata = {
                                    "query": tool_output.get("query", ""),
                                    "annotations": tool_output.get("annotations", []),
                                    "visited_urls": tool_output.get("visited_urls", []),
                                    "read_urls": tool_output.get("read_urls", []),
                                    "timestamp": tool_output.get("timestamp", ""),
                                    "usage": tool_output.get("usage", {}),
                                    "num_urls": tool_output.get("num_urls", 0),
                                }
                                result["research"] = research_metadata  # Add metadata to result
                                logger.info("Successfully extracted research findings and metadata.")
                                if not research_findings_content:
                                    logger.warning("Deep research tool returned empty findings.")
                                    result["metadata"]["errors"].append("Deep research tool returned empty findings.")
                            else:
                                logger.error(f"Deep research tool output was not a dict: {type(tool_output)}")
                                result["metadata"]["errors"].append("Deep research tool returned invalid output type.")
                        except Exception as e:
                            error_msg = f"Error extracting research findings: {e!s}"
                            logger.error(error_msg)
                            result["metadata"]["errors"].append(error_msg)

                    # Process schedule data if structure matches OR if tool name is correct
                    elif tool_name == "schedule_generator" or is_schedule_output:
                        logger.info(
                            f"[Memory Step {i + 1}] Matched tool: schedule_generator (Structure match: {is_schedule_output})"
                        )
                        try:
                            if not isinstance(tool_output, dict):
                                logger.error(f"Schedule tool output was not a dict after parsing: {type(tool_output)}")
                                continue

                            status_success = tool_output.get("status") == "success"

                            if status_success:
                                ics_content = tool_output.get("ics_content")
                                if ics_content:
                                    calendar_data = {"ics_content": ics_content}
                                    logger.info("Successfully extracted calendar ICS content.")  # Keep this
                                else:
                                    logger.warning(
                                        "Schedule generator output matched, but ics_content was empty or None."
                                    )
                            else:
                                error_msg = tool_output.get("message", "Schedule generator failed with no message.")
                                logger.error(
                                    f"Schedule generator output matched, but status was not success: {error_msg}"
                                )
                                result["metadata"]["errors"].append(f"Schedule Tool Error: {error_msg}")

                        except Exception as e:
                            error_msg = f"Error processing calendar data step: {e!s}"
                            logger.exception(error_msg)
                            result["metadata"]["errors"].append(error_msg)

                    # Log other tool calls if needed
                    else:
                        logger.info(
                            f"[Memory Step {i + 1}] Tool '{tool_name}' output processed (no specific handler). Output: {str(tool_output)[:200]}..."
                        )

                # Log steps that are not ActionSteps or don't have the required attributes
                else:
                    logger.debug(
                        f"[Memory Step {i + 1}] Skipping step (Type: {type(step)}), not a relevant ActionStep."
                    )

            # --- End Loop ---

            # --- Assign extracted calendar_data to result ---
            if calendar_data:
                result["calendar_data"] = calendar_data
                logger.info("Assigned calendar_data to final result.")

            # --- Extract the final answer text from the LLM response ---
            if hasattr(final_answer_obj, "text"):
                final_answer_from_llm = str(final_answer_obj.text).strip()
                logger.info("Extracted final answer from AgentResponse.text")
            elif isinstance(final_answer_obj, str):
                final_answer_from_llm = final_answer_obj.strip()
                logger.info("Extracted final answer from string")
            elif hasattr(final_answer_obj, "_value"):  # Check for older AgentText structure
                final_answer_from_llm = str(final_answer_obj._value).strip()
                logger.info("Extracted final answer from AgentText._value")
            elif hasattr(final_answer_obj, "answer"):  # Handle final_answer tool call argument
                # Check if the argument itself is the content string
                if isinstance(getattr(final_answer_obj, "answer", None), str):
                    final_answer_from_llm = str(final_answer_obj.answer).strip()
                    logger.info("Extracted final answer from final_answer tool argument string")
                # Or if it's nested in arguments (less likely for final_answer but check)
                elif (
                    isinstance(getattr(final_answer_obj, "arguments", None), dict)
                    and "answer" in final_answer_obj.arguments
                ):
                    final_answer_from_llm = str(final_answer_obj.arguments["answer"]).strip()
                    logger.info("Extracted final answer from final_answer tool arguments dict")
                else:
                    final_answer_from_llm = str(final_answer_obj).strip()
                    logger.warning(
                        f"Could not find specific answer attribute in final_answer object, using str(). Result: {final_answer_from_llm[:100]}..."
                    )

            else:
                final_answer_from_llm = str(final_answer_obj).strip()
                logger.warning(
                    f"Could not find specific answer attribute, using str(final_answer_obj). Result: {final_answer_from_llm[:100]}..."
                )

            # --- Determine the primary content for the email ---
            email_body_content = None
            if research_findings_content:
                logger.info("Prioritizing content from deep_research tool findings.")
                email_body_content = research_findings_content

            elif final_answer_from_llm:
                logger.info("Using final answer from LLM as email content (no deep_research output found).")
                email_body_content = final_answer_from_llm
            else:
                logger.warning("No content found from deep_research tool or final LLM answer.")
                # Fallback logic handled below

            # --- Format the selected content ---
            if email_body_content:
                # Remove signature remnants before formatting
                signature_markers = [
                    "Best regards,\nMXtoAI Assistant",
                    "Best regards,",
                    "Warm regards,",
                    "_Feel free to reply to this email to continue our conversation._",
                    "MXtoAI Assistant",
                    "> **Disclaimer:**",  # Remove Jina's disclaimer if present before our formatter adds its own signature
                ]
                for marker in signature_markers:
                    # Use regex for case-insensitive removal and handle potential leading/trailing spaces/newlines
                    email_body_content = re.sub(
                        r"^[\\s\\n]*" + re.escape(marker) + r".*$",
                        "",
                        email_body_content,
                        flags=re.IGNORECASE | re.MULTILINE,
                    ).strip()
                logger.debug("Removed potential signature remnants from email body content.")

                # Format using ReportFormatter
                result["email_content"]["text"] = self.report_formatter.format_report(
                    email_body_content, format_type="text", include_signature=True
                )
                result["email_content"]["html"] = self.report_formatter.format_report(
                    email_body_content, format_type="html", include_signature=True
                )

                # Default enhanced to base, remove old enhancement logic
                result["email_content"]["enhanced"]["text"] = result["email_content"]["text"]
                result["email_content"]["enhanced"]["html"] = result["email_content"]["html"]

                logger.debug("Formatted final email body content.")
            else:
                # Fallback if no content could be determined
                logger.error("No final answer text could be extracted or generated.")
                fallback_msg = "I apologize, but I encountered an issue generating the detailed response. Please try again later or contact support if this issue persists."
                result["email_content"]["html"] = self.report_formatter.format_report(
                    fallback_msg, format_type="html", include_signature=True
                )
                result["email_content"]["text"] = self.report_formatter.format_report(
                    fallback_msg, format_type="text", include_signature=True
                )
                result["email_content"]["enhanced"]["html"] = result["email_content"]["html"]
                result["email_content"]["enhanced"]["text"] = result["email_content"]["text"]
                result["metadata"]["errors"].append("No final answer text was generated or extracted")
                result["metadata"]["email_sent"]["status"] = "error"
                result["metadata"]["email_sent"]["error"] = "No reply text was generated"

            logger.debug(
                f"Final processing result before return: { {k: (v if k != 'email_content' else '...') for k, v in result.items()} }"
            )  # Avoid logging large email content
            return result

        except Exception as e:
            logger.exception(f"Critical error in _process_agent_result: {e!s}")
            # ... (existing error handling remains the same) ...
            error_result = {
                "metadata": {
                    "processed_at": datetime.now().isoformat(),
                    "mode": "unknown",
                    "errors": [f"Critical error in _process_agent_result: {e!s}"],
                    "email_sent": {
                        "status": "error",
                        "error": f"Critical error: {e!s}",
                        "timestamp": datetime.now().isoformat(),
                    },
                },
                "email_content": {
                    "html": self.report_formatter.format_report(
                        "I encountered a critical error processing your request.",
                        format_type="html",
                        include_signature=True,
                    ),
                    "text": self.report_formatter.format_report(
                        "I encountered a critical error processing your request.",
                        format_type="text",
                        include_signature=True,
                    ),
                    "enhanced": {"html": None, "text": None},
                },
                "attachments": {"summary": None, "processed": []},
                "calendar_data": None,
                "research": None,  # Ensure research key exists even on error
            }
            logger.debug(f"Final processing error result before return: {error_result}")
            return error_result

    def process_email(
        self,
        email_request: EmailRequest,
        email_instructions: "EmailHandleInstructions",  # Type hint as string to avoid circular import
    ) -> dict[str, Any]:
        """
        Process an email using the agent based on the provided email handle instructions.

        Args:
            email_request: EmailRequest instance containing email data
            email_instructions: EmailHandleInstructions object containing processing configuration

        Returns:
            Dictionary with processing results including any error information

        """
        try:
            # Update the model's current handle
            self.routed_model.current_handle = email_instructions

            # Create task with specific instructions
            task = self._create_task(email_request, email_instructions)

            # Run the agent
            try:
                logger.info("Starting agent execution...")
                final_answer_obj = self.agent.run(task)
                logger.info("Agent execution completed.")

                # --- Get steps from agent memory ---
                agent_steps = list(self.agent.memory.steps)  # Use memory.steps
                logger.info(f"Captured {len(agent_steps)} steps from agent memory.")
                # Log first few steps types for debugging
                # for i, step in enumerate(agent_steps):
                #     if i < 5:
                #          logger.info(f"[Memory Step {i+1}] Type: {type(step)}")
                #     else:
                #         break

                logger.info(f"Final answer object type: {type(final_answer_obj)}")
                # logger.info(f"Final answer object dir: {dir(final_answer_obj)}") # <-- REMOVE THIS
                # --- End logging ---

                # --- Pass final answer object AND steps ---
                processed_result = self._process_agent_result(final_answer_obj, agent_steps)  # Pass steps

                # Ensure we have a reply for email sending
                if not processed_result.get("email_content") or not processed_result["email_content"].get("text"):
                    msg = "No reply text was generated by _process_agent_result"
                    logger.error(msg)
                    # Populate errors within the existing structure if possible
                    if "metadata" not in processed_result:
                        processed_result["metadata"] = {}
                    if "errors" not in processed_result["metadata"]:
                        processed_result["metadata"]["errors"] = []
                    processed_result["metadata"]["errors"].append(msg)
                    if "email_sent" not in processed_result["metadata"]:
                        processed_result["metadata"]["email_sent"] = {}
                    processed_result["metadata"]["email_sent"]["status"] = "error"
                    processed_result["metadata"]["email_sent"]["error"] = msg
                    # Return the partially processed result with error flags
                    return processed_result

                logger.info(f"Email processed successfully with handle: {email_instructions.handle}")
                return processed_result

            except Exception as e:
                error_msg = f"Error during agent processing: {e!s}"
                logger.error(error_msg)

                # Generate a basic response when agent fails
                return {
                    "attachments": {"summary": None, "attachments": []},
                    "summary": None,
                    "email_content": {"html": None, "text": None},
                    "processed_at": datetime.now().isoformat(),
                    "handle": email_instructions.handle,
                    "errors": [error_msg],
                    "email_sent": {"status": "error", "timestamp": datetime.now().isoformat(), "error": error_msg},
                }

        except Exception as e:
            error_msg = f"Critical error in email processing: {e!s}"
            logger.error(error_msg, exc_info=True)

            # Ensure we always return a response, even in case of critical failure
            return {
                "attachments": {"summary": None, "attachments": []},
                "summary": None,
                "email_content": {"html": None, "text": None},
                "processed_at": datetime.now().isoformat(),
                "handle": email_instructions.handle,
                "errors": [error_msg],
                "email_sent": {"status": "error", "timestamp": datetime.now().isoformat(), "error": error_msg},
            }
