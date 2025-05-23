import ast
import datetime
import re
from typing import Any, Optional

from loguru import logger

from mxtoai.llm_utils import RoutedChatOpenAI
from mxtoai.prompts.base_prompts import (
    LIST_FORMATTING_REQUIREMENTS,
    MARKDOWN_STYLE_GUIDE,
    RESEARCH_GUIDELINES,
    RESPONSE_GUIDELINES,
)
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
    ProcessingInstructions,
    ProcessingMetadata,
    ReportFormatter,
)
from mxtoai.tool_utils import create_tools, initialize_agent_memory, setup_agent_executor

# Placeholder for the actual datetime if it's used directly
# from datetime import datetime, timezone # Already imported via `import datetime`


class EmailAgent:
    def __init__(
        self, attachment_dir: str = "email_attachments", *, verbose: bool = False, enable_deep_research: bool = False
    ):
        self.attachment_dir = attachment_dir
        self.verbose = verbose
        self.report_formatter = ReportFormatter()
        self.enable_deep_research = enable_deep_research

        self.routed_model = RoutedChatOpenAI(temperature=0.1, model_kwargs={"seed": 42})
        self.tools = create_tools(self.attachment_dir, enable_deep_research=self.enable_deep_research)
        self.memory = initialize_agent_memory(self.routed_model.model)
        self.agent = setup_agent_executor(self.routed_model.model, self.tools, self.memory, verbose=self.verbose)

    def _init_agent(self):
        # Re-initialize or reset parts of the agent if necessary
        self.memory.clear()  # Clear memory for a new run
        # Potentially re-initialize other stateful components if they exist
        logger.info("Agent re-initialized for a new request.")

    def _create_task(self, email_request: EmailRequest, email_instructions: ProcessingInstructions) -> str:
        # Ensure agent is re-initialized for each new task
        self._init_agent()

        email_context = self._create_email_context(
            email_request, attachment_details=email_request.decoded_attachments
        )
        attachment_task_str = self._create_attachment_task(email_request.decoded_attachments)

        output_template = email_instructions.output_template or ""
        deep_research_mandatory = email_instructions.deep_research_mandatory or False

        # Always add schedule_generator to tools if not present
        if not any(tool.name == "schedule_generator" for tool in self.tools):
            # This assumes create_tools can be called to get specific tools or a way to add it.
            # For simplicity, let's assume tools are fixed after init for now or handled in create_tools.
            logger.warning("schedule_generator tool not explicitly added, relying on initial setup.")

        return self._create_task_template(
            handle=email_instructions.handle,
            email_context=email_context,
            handle_specific_template=email_instructions.template,
            attachment_task=attachment_task_str,
            deep_research_mandatory=deep_research_mandatory,
            output_template=output_template,
        )

    def _format_attachments(self, attachments: list[EmailAttachment]) -> list[str]:
        if not attachments:
            return []
        return [
            f"- {att.filename} ({att.content_type}, {att.size} bytes)" for att in attachments if att.filename
        ]

    def _create_email_context(self, email_request: EmailRequest, attachment_details=None) -> str:
        formatted_attachments = []
        if attachment_details: # Check if attachment_details is not None
            # Assuming attachment_details is a list of strings or can be processed into one
            if isinstance(attachment_details, list) and all(isinstance(item, str) for item in attachment_details):
                formatted_attachments = attachment_details
            elif isinstance(attachment_details, list) and all(isinstance(item, dict) for item in attachment_details):
                # If it's a list of dicts (like DecodedAttachment), extract relevant info
                 formatted_attachments = [
                    f"- {att.get('filename', 'N/A')} ({att.get('content_type', 'N/A')}, {att.get('size', 0)} bytes)"
                    for att in attachment_details
                ]

        return f"""
From: {email_request.from_email}
To: {email_request.to_email}
Cc: {email_request.cc_email}
Bcc: {email_request.bcc_email}
Subject: {email_request.subject}
Date: {email_request.date}
Message ID: {email_request.message_id}
Reply-To: {email_request.reply_to}

Attachments:
{formatted_attachments if formatted_attachments else "No attachments."}

Body:
{email_request.body}
"""

    def _create_attachment_task(self, attachment_details: list[str]) -> str:
        return (
            "Process these attachments and use their content: \\n" + "\\n".join(attachment_details)
            if attachment_details
            else ""
        )

    def _create_task_template(
        self,
        handle: str,
        email_context: str,
        handle_specific_template: str = "",
        attachment_task: str = "",
        *,
        deep_research_mandatory: bool = False,
        output_template: str = "",
    ) -> str:
        sections = [
            f"Task: Process for handle '{handle}'.",
            handle_specific_template,
            "Email Context:",
            email_context,
            RESEARCH_GUIDELINES["mandatory"] if deep_research_mandatory else RESEARCH_GUIDELINES["optional"],
            attachment_task,
            output_template,
            RESPONSE_GUIDELINES,
            MARKDOWN_STYLE_GUIDE,
            LIST_FORMATTING_REQUIREMENTS,
        ]
        return "\\n\\n".join(filter(None, sections))

    def _parse_tool_output(self, tool_name: str, tool_output: Any, errors_list: list[ProcessingError], step_idx_str: str) -> Any:
        """Helper to parse tool output string to dict if needed."""
        needs_parsing = tool_name in ["schedule_generator", "attachment_processor", "deep_research"]
        if isinstance(tool_output, str) and needs_parsing:
            try:
                return ast.literal_eval(tool_output)
            except (ValueError, SyntaxError) as e:
                msg = f"Failed to parse '{tool_name}' output: {e!s}. Content: {tool_output[:200]}..."
                logger.error(f"[{step_idx_str}] {msg}")
                errors_list.append(ProcessingError(message=f"Failed to parse {tool_name} output", details=str(e)))
                return None
            except Exception as e: # pylint: disable=broad-except
                msg = f"Unexpected error parsing '{tool_name}' output: {e!s}. Content: {tool_output[:200]}..."
                logger.error(f"[{step_idx_str}] {msg}")
                errors_list.append(ProcessingError(message=f"Unexpected error parsing {tool_name} output", details=str(e)))
                return None
        return tool_output

    def _process_attachment_processor_output(
        self, tool_output: dict, processed_attachment_details: list[ProcessedAttachmentDetail]
    ) -> Optional[str]:
        """Processes output from the attachment_processor tool."""
        attachment_proc_summary = tool_output.get("summary")
        for attachment_data in tool_output.get("attachments", []):
            pa_detail = ProcessedAttachmentDetail(
                filename=attachment_data.get("filename", "unknown_attachment"),
                type=attachment_data.get("type", "application/octet-stream"),
                size=attachment_data.get("size", 0),
                content=attachment_data.get("content"),
                summary=attachment_data.get("summary", ""),
                error=attachment_data.get("error"),
            )
            if "content" in attachment_data and isinstance(attachment_data["content"], dict) and attachment_data["content"].get("caption"):
                pa_detail.caption = attachment_data["content"]["caption"]
            processed_attachment_details.append(pa_detail)
        return attachment_proc_summary

    def _process_deep_research_output(
        self, tool_output: dict, errors_list: list[ProcessingError]
    ) -> tuple[Optional[str], Optional[AgentResearchMetadata]]:
        """Processes output from the deep_research tool."""
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
        return research_output_findings, research_output_metadata

    def _process_schedule_generator_output(
        self, tool_output: dict, errors_list: list[ProcessingError]
    ) -> Optional[CalendarResult]:
        """Processes output from the schedule_generator tool."""
        if tool_output.get("status") == "success" and tool_output.get("ics_content"):
            return CalendarResult(ics_content=tool_output["ics_content"])

        error_msg = tool_output.get("message", "Schedule generator failed or missing ICS content.")
        errors_list.append(ProcessingError(message="Schedule Tool Error", details=error_msg))
        return None

    def _get_tool_name_and_raw_output_from_step(self, step: Any, step_idx_str: str) -> tuple[Optional[str], Any]:
        """Extracts tool name and raw output from an agent step."""
        tool_name: Optional[str] = None
        raw_tool_output: Any = None

        if hasattr(step, "tool_calls") and isinstance(step.tool_calls, list) and len(step.tool_calls) > 0:
            first_tool_call = step.tool_calls[0]
            tool_name = getattr(first_tool_call, "name", None)
            if not tool_name:
                logger.warning(f"[{step_idx_str}] Could not extract tool name from first tool_call.")

            # Prefer action_output if available, otherwise observations
            action_out = getattr(step, "action_output", None)
            obs_out = getattr(step, "observations", None)

            if action_out is not None:
                raw_tool_output = action_out
            elif obs_out is not None:
                # If observations is a list and not empty, take the first one.
                if isinstance(obs_out, list) and len(obs_out) > 0:
                    raw_tool_output = obs_out[0]
                elif not isinstance(obs_out, list): # If it's not a list, use as is
                    raw_tool_output = obs_out
                else: # It's an empty list
                    logger.warning(f"[{step_idx_str}] Tool '{tool_name or 'Unknown Tool'}' observations list is empty.")

        if not tool_name and hasattr(step, "action") and hasattr(step.action, "tool"): # Another common pattern for tool name
            tool_name = step.action.tool
            # For this pattern, output is often in step.observation
            if raw_tool_output is None and hasattr(step, "observation"): # Check step.observation if action_output was None
                 raw_tool_output = step.observation


        return tool_name, raw_tool_output

    def _extract_tool_outputs_from_steps(
        self, agent_steps: list, errors_list: list[ProcessingError]
    ) -> tuple[
        Optional[str],
        list[ProcessedAttachmentDetail],
        Optional[CalendarResult],
        Optional[str],
        Optional[AgentResearchMetadata],
    ]:
        attachment_proc_summary: Optional[str] = None
        processed_attachment_details: list[ProcessedAttachmentDetail] = []
        calendar_result_data: Optional[CalendarResult] = None
        research_output_findings: Optional[str] = None
        research_output_metadata: Optional[AgentResearchMetadata] = None

        for i, step in enumerate(agent_steps):
            step_idx_str = f"Memory Step {i + 1}"
            logger.info(f"[{step_idx_str}] Raw Step Type: {type(step)}")

            tool_name, raw_tool_output = self._get_tool_name_and_raw_output_from_step(step, step_idx_str)

            if not tool_name or raw_tool_output is None:
                logger.debug(
                    f"[{step_idx_str}] Skipping step. Could not identify tool name or raw output. Step details: {str(step)[:200]}"
                )
                continue

            logger.info(f"[{step_idx_str}] Identified Tool: '{tool_name}', Raw Output Type: '{type(raw_tool_output)}'")
            tool_output = self._parse_tool_output(tool_name, raw_tool_output, errors_list, step_idx_str)

            if tool_output is None and tool_name in ["schedule_generator", "attachment_processor", "deep_research"]: # Parsing failed or tool returned None explicitly
                logger.warning(f"[{step_idx_str}] Parsed output for '{tool_name}' is None. Skipping specific processing.")
                continue

            logger.info(f"[{step_idx_str}] Processing tool '{tool_name}', Parsed Output Type: '{type(tool_output)}'")

            if tool_name == "attachment_processor" and isinstance(tool_output, dict):
                attachment_proc_summary = self._process_attachment_processor_output(tool_output, processed_attachment_details)
            elif tool_name == "deep_research" and isinstance(tool_output, dict):
                research_output_findings, research_output_metadata = self._process_deep_research_output(tool_output, errors_list)
            elif tool_name == "schedule_generator" and isinstance(tool_output, dict):
                calendar_result_data = self._process_schedule_generator_output(tool_output, errors_list)
            else:
                logger.info(f"[{step_idx_str}] Tool '{tool_name}' output (Type: {type(tool_output)}) processed (no specific handler or not a dict).")

        return (
            attachment_proc_summary,
            processed_attachment_details,
            calendar_result_data,
            research_output_findings,
            research_output_metadata,
        )

    def _extract_final_answer_text(self, final_answer_obj: Any) -> Optional[str]:
        final_answer_from_llm: Optional[str] = None
        if isinstance(final_answer_obj, str):
            final_answer_from_llm = final_answer_obj.strip()
        elif hasattr(final_answer_obj, "_value"):
            final_answer_from_llm = str(getattr(final_answer_obj, "_value", "")).strip()
        elif hasattr(final_answer_obj, "answer") and isinstance(getattr(final_answer_obj, "answer", None), str):
            final_answer_from_llm = str(final_answer_obj.answer).strip()
        elif isinstance(final_answer_obj, dict) and "output" in final_answer_obj:
            final_answer_from_llm = str(final_answer_obj["output"]).strip()
        else:
            final_answer_from_llm = str(final_answer_obj).strip()
            logger.warning(
                f"Could not find specific answer attribute in final_answer object, using str(). Result: {final_answer_from_llm[:100]}..."
            )
        return final_answer_from_llm if final_answer_from_llm else None

    def _prepare_email_body(
        self,
        email_body_content_source: Optional[str],
        errors_list: list[ProcessingError],
        email_sent_status: EmailSentStatus,
    ) -> tuple[Optional[str], Optional[str]]:
        email_text_content: Optional[str] = None
        email_html_content: Optional[str] = None

        if email_body_content_source:
            signature_markers = [
                "Best regards,\\nMXtoAI Assistant",
                "Best regards,",
                "Warm regards,",
                "_Feel free to reply to this email to continue our conversation._",
                "MXtoAI Assistant",
                "> **Disclaimer:**",
            ]
            temp_content = email_body_content_source
            for marker in signature_markers:
                temp_content = re.sub(
                    r"^[\\s\\n]*" + re.escape(marker) + r".*$", "", temp_content, flags=re.IGNORECASE | re.MULTILINE
                ).strip()

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

        return email_text_content, email_html_content

    def _build_error_processing_result(
        self,
        e: Exception,
        processed_at_time: str,
        current_email_handle: str,
        errors_list: list[ProcessingError],
        email_sent_status: EmailSentStatus,
        email_text_content: Optional[str],
        email_html_content: Optional[str],
        attachment_proc_summary: Optional[str],
        processed_attachment_details: list[ProcessedAttachmentDetail],
        calendar_result_data: Optional[CalendarResult],
        research_output_findings: Optional[str],
        research_output_metadata: Optional[AgentResearchMetadata],
    ) -> DetailedEmailProcessingResult:
        logger.exception("Critical error in _process_agent_result")
        errors_list.append(ProcessingError(message="Critical error in _process_agent_result", details=str(e)))

        current_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if email_sent_status.status != "error":
            email_sent_status.status = "error"
            email_sent_status.error = f"Critical error in _process_agent_result: {e!s}"
            email_sent_status.timestamp = current_timestamp

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

    def _process_agent_result(
        self, final_answer_obj: Any, agent_steps: list, current_email_handle: str
    ) -> DetailedEmailProcessingResult:
        processed_at_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        errors_list: list[ProcessingError] = []
        email_sent_status = EmailSentStatus(status="pending", timestamp=processed_at_time)

        # Initialize all potential result components to None or empty
        attachment_proc_summary: Optional[str] = None
        processed_attachment_details: list[ProcessedAttachmentDetail] = []
        calendar_result_data: Optional[CalendarResult] = None
        research_output_findings: Optional[str] = None
        research_output_metadata: Optional[AgentResearchMetadata] = None
        email_text_content: Optional[str] = None
        email_html_content: Optional[str] = None

        try:
            logger.info(f"Processing final answer object type: {type(final_answer_obj)}")
            logger.info(f"Processing {len(agent_steps)} agent step entries.")

            (
                attachment_proc_summary,
                processed_attachment_details,
                calendar_result_data,
                research_output_findings,
                research_output_metadata,
            ) = self._extract_tool_outputs_from_steps(agent_steps, errors_list)

            final_answer_from_llm = self._extract_final_answer_text(final_answer_obj)

            email_body_content_source = research_output_findings if research_output_findings else final_answer_from_llm
            email_text_content, email_html_content = self._prepare_email_body(
                email_body_content_source, errors_list, email_sent_status
            )

            processed_result = DetailedEmailProcessingResult(
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

            if not processed_result.email_content or not processed_result.email_content.text:
                msg = "No reply text was generated by _process_agent_result"
                logger.error(msg)
                processed_result.metadata.errors.append(ProcessingError(message=msg))
                processed_result.metadata.email_sent.status = "error"
                processed_result.metadata.email_sent.error = msg

                logger.info(f"Email processed (but no reply text generated) with handle: {current_email_handle}")
                return processed_result
            logger.info(f"Email processed successfully with handle: {current_email_handle}")
            return processed_result

        except Exception as e:
            return self._build_error_processing_result(
                e,
                processed_at_time,
                current_email_handle,
                errors_list,
                email_sent_status,
                email_text_content,
                email_html_content,
                attachment_proc_summary,
                processed_attachment_details,
                calendar_result_data,
                research_output_findings,
                research_output_metadata,
            )
        else:
            logger.info(f"Email processed successfully with handle: {current_email_handle}")
            return processed_result

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
            final_answer_obj = self.agent.run(task)
            logger.info("Agent execution completed.")

            agent_steps = list(self.agent.memory.steps)
            logger.info(f"Captured {len(agent_steps)} steps from agent memory.")

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

        except Exception as e:
            error_msg = f"Critical error in email processing: {e!s}"
            logger.exception(error_msg)

            # Construct a DetailedEmailProcessingResult for error cases
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
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
            )
        else:
            logger.info(f"Email processed successfully with handle: {email_instructions.handle}")
            return processed_result
