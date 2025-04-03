import os
from datetime import datetime
from typing import Any, Optional

from dotenv import load_dotenv

# Update imports to use proper classes from smolagents
from smolagents import ToolCallingAgent

from mxtoai._logging import get_logger
from mxtoai.prompts.base_prompts import create_attachment_processing_task, create_email_context, create_task_template
from mxtoai.routed_litellm_model import RoutedLiteLLMModel
from mxtoai.schemas import EmailRequest
from mxtoai.scripts.report_formatter import ReportFormatter
from mxtoai.scripts.visual_qa import azure_visualizer
from mxtoai.tools.attachment_processing_tool import AttachmentProcessingTool
from mxtoai.tools.deep_research_tool import DeepResearchTool

# Load environment variables
load_dotenv(override=True)

# Configure logger
logger = get_logger("email_agent")

# Custom role conversions for the model
custom_role_conversions = {"tool-call": "assistant", "tool-response": "user"}

class EmailAgent:
    """
    Email processing agent that can summarize, reply to, and research information for emails.
    """

    def __init__(
        self,
        azure_openai_model: Optional[str] = None,
        azure_openai_api_key: Optional[str] = None,
        azure_openai_endpoint: Optional[str] = None,
        api_version: Optional[str] = None,
        attachment_dir: str = "email_attachments",
        verbose: bool = False,
        enable_deep_research: bool = False
    ):
        """
        Initialize the email agent with tools for different operations.

        Args:
            azure_openai_model: Azure OpenAI model name (deprecated)
            azure_openai_api_key: Azure OpenAI API key (deprecated)
            azure_openai_endpoint: Azure OpenAI endpoint (deprecated)
            api_version: API version for Azure OpenAI (deprecated)
            attachment_dir: Directory to store email attachments
            verbose: Whether to enable verbose logging
            enable_deep_research: Whether to enable Jina AI deep research functionality (uses API tokens)

        """
        # TODO: fix this laater
        # # Set up logging
        # if verbose:
        #     logger.setLevel(logging.DEBUG)

        # Create attachment directory
        self.attachment_dir = attachment_dir
        os.makedirs(self.attachment_dir, exist_ok=True)

        # Initialize tools
        self.attachment_tool = AttachmentProcessingTool()
        self.report_formatter = ReportFormatter()  # Initialize the report formatter

        # Initialize deep research tool if JINA_API_KEY is available
        self.research_tool = None
        if os.getenv("JINA_API_KEY"):
            self.research_tool = DeepResearchTool()
            # Enable deep research if explicitly requested
            if enable_deep_research:
                self.research_tool.enable_deep_research()
                logger.info("Deep research functionality enabled during initialization")

        # Collect tools to be used with the agent
        self.available_tools = [self.attachment_tool, azure_visualizer]
        if self.research_tool:
            self.available_tools.append(self.research_tool)

        # Initialize the agent
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
            description="An agent that processes emails, generates summaries, replies, and conducts research with advanced capabilities.",
            provide_run_summary=True
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
            "ask": "full"  # General prompt handle defaults to full processing
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

    def _process_attachments(self, attachments: list[dict[str, Any]]) -> dict[str, Any]:
        """Process attachments using appropriate tools based on file type."""
        processed_results = {
            "attachments": [],
            "summary": "",
            "errors": []  # Track any errors during processing
        }

        if not attachments:
            return processed_results

        # Separate attachments by type
        image_attachments = []
        other_attachments = []

        for attachment in attachments:
            # Ensure we have required fields
            if not all(key in attachment for key in ["filename", "contentType", "path", "size"]):
                error_msg = f"Missing required fields in attachment: {attachment}"
                logger.error(error_msg)
                processed_results["errors"].append(error_msg)
                continue

            if attachment["contentType"].startswith("image/"):
                image_attachments.append(attachment)
            else:
                other_attachments.append(attachment)

        # Process non-image attachments
        if other_attachments:
            try:
                doc_results = self.attachment_tool.forward(other_attachments, mode="basic")
                processed_results["attachments"].extend(doc_results["attachments"])
            except Exception as e:
                error_msg = f"Failed to process document attachments: {e!s}"
                logger.error(error_msg)
                processed_results["errors"].append(error_msg)

        # Process image attachments
        for img_attachment in image_attachments:
            try:
                caption = azure_visualizer(img_attachment["path"])
                processed_results["attachments"].append({
                    **img_attachment,
                    "content": {
                        "text": caption,
                        "type": "image"
                    }
                })
                logger.info(f"Successfully processed image: {img_attachment['filename']}")
            except Exception as e:
                error_msg = f"Failed to process image {img_attachment['filename']}: {e!s}"
                logger.error(error_msg)
                processed_results["errors"].append(error_msg)
                processed_results["attachments"].append({
                    **img_attachment,
                    "content": {
                        "text": "Sorry, I was unable to process this image.",
                        "type": "image",
                        "error": str(e)
                    }
                })

        # Create summary including any errors
        successful = len(processed_results["attachments"])
        failed = len(processed_results["errors"])
        summary_parts = [f"Processed {successful} attachments ({len(image_attachments)} images, {len(other_attachments)} documents)"]

        if failed > 0:
            summary_parts.append(f"Failed to process {failed} attachments")

        processed_results["summary"] = ". ".join(summary_parts)

        return processed_results

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
            deep_research_mandatory=email_instructions.deep_research_mandatory
        )

    def _process_agent_result(self, agent_result: Any) -> dict[str, Any]:
        """
        Process the agent's result into our expected format.

        Returns a streamlined response structure with:
        - email_content: Contains both HTML and text versions for email sending
        - attachments: Processed attachment information (sanitized)
        - metadata: Processing information and status
        """
        # Initialize all required variables at the start
        attachment_summaries = {
            "text": [],
            "html": []
        }

        result = {
            "metadata": {
                "processed_at": datetime.now().isoformat(),
                "mode": getattr(agent_result, "mode", "full"),
                "errors": [],
                "email_sent": {
                    "status": "pending",
                    "timestamp": datetime.now().isoformat()
                }
            },
            "email_content": {
                "html": None,
                "text": None,
                "enhanced": {  # Pre-processed versions with attachment summaries
                    "html": None,
                    "text": None
                }
            },
            "attachments": {
                "summary": None,
                "processed": []  # Will contain sanitized attachment info
            }
        }

        try:
            research_content = None
            # Process attachments and research first
            if hasattr(agent_result, "steps"):
                for step in agent_result.steps:
                    # Process attachment results
                    if hasattr(step, "tool_name") and step.tool_name == "attachment_processor" and hasattr(step, "tool_output"):
                        try:
                            att_output = step.tool_output
                            if isinstance(att_output, dict):
                                result["attachments"]["summary"] = att_output.get("summary")

                                # Process and sanitize each attachment
                                for attachment in att_output.get("attachments", []):
                                    # Create sanitized version
                                    sanitized_att = {
                                        "filename": attachment.get("filename", ""),
                                        "size": attachment.get("size", 0),
                                        "type": attachment.get("type", "unknown")
                                    }

                                    # Handle errors
                                    if "error" in attachment:
                                        sanitized_att["error"] = attachment["error"]
                                        result["metadata"]["errors"].append(f"Error processing {sanitized_att['filename']}: {attachment['error']}")
                                        continue

                                    # Process content for email enhancement
                                    if "content" in attachment:
                                        content = attachment["content"]
                                        if isinstance(content, dict):
                                            # For text documents
                                            if content.get("text"):
                                                text = str(content["text"])
                                                if len(text) > 500:
                                                    text = text[:497] + "..."

                                                attachment_summaries["text"].append(
                                                    f"\n\nSummary of {sanitized_att['filename']}\n{text}"
                                                )
                                                attachment_summaries["html"].append(
                                                    f"<h3>Summary of {sanitized_att['filename']}</h3><p>{text}</p>"
                                                )

                                            # For images
                                            elif content.get("caption"):
                                                sanitized_att["caption"] = content["caption"]
                                                attachment_summaries["text"].append(
                                                    f"\n\nDescription of {sanitized_att['filename']}\n{content['caption']}"
                                                )
                                                attachment_summaries["html"].append(
                                                    f"<h3>Description of {sanitized_att['filename']}</h3><p>{content['caption']}</p>"
                                                )

                                    result["attachments"]["processed"].append(sanitized_att)

                        except Exception as e:
                            error_msg = f"Error processing attachment results: {e!s}"
                            logger.error(error_msg)
                            result["metadata"]["errors"].append(error_msg)

                    # Store research results if available
                    if hasattr(step, "tool_name") and step.tool_name == "deep_research" and hasattr(step, "tool_output"):
                        try:
                            research_output = step.tool_output
                            # Store the complete research findings for preservation
                            research_content = research_output.get("findings", "")
                            result["research"] = {
                                "query": research_output.get("query", ""),
                                "findings": research_content,
                                "sources": research_output.get("visited_urls", []),
                                "timestamp": research_output.get("timestamp", "")
                            }
                            logger.info("Successfully extracted research findings")
                        except Exception as e:
                            error_msg = f"Error extracting research findings: {e!s}"
                            logger.error(error_msg)
                            result["metadata"]["errors"].append(error_msg)

            # Get the final answer from the agent result
            final_answer = None
            if isinstance(agent_result, str):
                final_answer = agent_result.strip()
            elif hasattr(agent_result, "answer"):
                final_answer = str(agent_result.answer).strip()

            if final_answer:
                # Remove any existing signature if present
                signature_markers = [
                    "Best regards,\nMXtoAI Assistant",
                    "Best regards,",
                    "Warm regards,",
                    "_Feel free to reply to this email to continue our conversation._",
                    "MXtoAI Assistant"
                ]
                for marker in signature_markers:
                    final_answer = final_answer.replace(marker, "").strip()

                # If we have research content and it's not already in the final answer,
                # ensure it's included in the response
                if research_content and research_content not in final_answer:
                    # Find a suitable position to insert the research content
                    # Look for common section markers
                    insert_markers = [
                        "\n## Research Findings",
                        "\n## Detailed Analysis",
                        "\n## Results",
                        "\n\nBased on my research",
                        "\n\nHere are my findings"
                    ]

                    insert_pos = -1
                    for marker in insert_markers:
                        pos = final_answer.find(marker)
                        if pos != -1:
                            insert_pos = pos
                            break

                    if insert_pos != -1:
                        # Insert at the found position
                        final_answer = (
                            final_answer[:insert_pos] +
                            "\n\n" + research_content +
                            final_answer[insert_pos:]
                        )
                    else:
                        # Append to the end before any signature
                        signature_pos = float("inf")
                        for marker in signature_markers:
                            pos = final_answer.find(marker)
                            if pos != -1:
                                signature_pos = min(signature_pos, pos)

                        if signature_pos != float("inf"):
                            final_answer = (
                                final_answer[:signature_pos] +
                                "\n\n" + research_content +
                                "\n\n" +
                                final_answer[signature_pos:]
                            )
                        else:
                            final_answer += "\n\n" + research_content

                # Format base response in both HTML and plain text
                result["email_content"]["html"] = self.report_formatter.format_report(
                    final_answer,
                    format_type="html",
                    include_signature=True  # We'll add signature here
                )
                result["email_content"]["text"] = self.report_formatter.format_report(
                    final_answer,
                    format_type="text",
                    include_signature=True  # We'll add signature here
                )

                # Create enhanced versions with attachment summaries
                if attachment_summaries["text"]:
                    enhanced_text = result["email_content"]["text"]
                    # Insert attachment summaries before the signature
                    signature_pos = enhanced_text.find("Best regards,")
                    if signature_pos != -1:
                        enhanced_text = (
                            enhanced_text[:signature_pos] +
                            "\n\nHere's what I found in your attachments:" +
                            "".join(attachment_summaries["text"]) +
                            "\n\n" +
                            enhanced_text[signature_pos:]
                        )
                    else:
                        enhanced_text += "\n\nHere's what I found in your attachments:" + "".join(attachment_summaries["text"])

                    result["email_content"]["enhanced"]["text"] = enhanced_text

                    # Insert attachment summaries before the closing body tag in HTML
                    if result["email_content"]["html"] and attachment_summaries["html"]:
                        enhanced_html = result["email_content"]["html"].replace(
                            "</body>",
                            "<h2>Attachment Analysis</h2>" + "".join(attachment_summaries["html"]) + "</body>"
                        )
                        result["email_content"]["enhanced"]["html"] = enhanced_html
                else:
                    # If no attachment summaries, enhanced versions are same as base versions
                    result["email_content"]["enhanced"]["text"] = result["email_content"]["text"]
                    result["email_content"]["enhanced"]["html"] = result["email_content"]["html"]

                logger.debug("Formatted response in both HTML and plain text with attachment summaries")
            else:
                logger.warning("No reply was generated from the result")
                # Provide a graceful fallback message
                fallback_msg = (
                    "I apologize, but I was unable to generate a proper response at this time. "
                    "Please try again later or contact support if this issue persists."
                )

                # Format fallback message
                result["email_content"]["html"] = self.report_formatter.format_report(
                    fallback_msg,
                    format_type="html",
                    include_signature=True
                )
                result["email_content"]["text"] = self.report_formatter.format_report(
                    fallback_msg,
                    format_type="text",
                    include_signature=True
                )

                # Use same content for enhanced versions
                result["email_content"]["enhanced"]["html"] = result["email_content"]["html"]
                result["email_content"]["enhanced"]["text"] = result["email_content"]["text"]

                result["metadata"]["errors"].append("No reply was generated from the agent")
                result["metadata"]["email_sent"]["status"] = "error"
                result["metadata"]["email_sent"]["error"] = "No reply text was generated"

            return result

        except Exception as e:
            error_msg = f"Error processing agent result: {e!s}"
            logger.error(error_msg)

            # Return a structured error response
            return {
                "metadata": {
                    "processed_at": datetime.now().isoformat(),
                    "mode": getattr(agent_result, "mode", "full"),
                    "errors": [error_msg],
                    "email_sent": {
                        "status": "error",
                        "error": error_msg,
                        "timestamp": datetime.now().isoformat()
                    }
                },
                "email_content": {
                    "html": self.report_formatter.format_report(
                        "I apologize, but I encountered an error while processing your request. "
                        "Please try again later or contact support if this issue persists.",
                        format_type="html",
                        include_signature=True
                    ),
                    "text": self.report_formatter.format_report(
                        "I apologize, but I encountered an error while processing your request. "
                        "Please try again later or contact support if this issue persists.",
                        format_type="text",
                        include_signature=True
                    ),
                    "enhanced": {
                        "html": None,
                        "text": None
                    }
                },
                "attachments": {
                    "summary": None,
                    "processed": []
                }
            }

    def process_email(
        self,
        email_request: EmailRequest,
        email_instructions: "EmailHandleInstructions"  # Type hint as string to avoid circular import
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

            # Process attachments first if required
            if email_instructions.process_attachments and email_request.attachments:
                try:
                    attachment_results = self._process_attachments([att.model_dump() for att in email_request.attachments])
                    if attachment_results.get("errors"):
                        logger.warning(f"Attachment processing errors: {attachment_results['errors']}")
                except Exception as e:
                    logger.exception(f"Error processing attachments: {e!s}")

            # Create task with specific instructions
            task = self._create_task(email_request, email_instructions)

            # Run the agent
            try:
                result = self.agent.run(task)
                logger.debug("Agent execution completed")
                processed_result = self._process_agent_result(result)

                # Ensure we have a reply for email sending
                if not processed_result.get("email_content"):
                    msg = "No reply text was generated"
                    raise ValueError(msg)

                logger.info(f"Email processed successfully with handle: {email_instructions.handle}")
                return processed_result

            except Exception as e:
                error_msg = f"Error during agent processing: {e!s}"
                logger.error(error_msg)

                # Generate a basic response when agent fails
                return {
                    "attachments": {"summary": None, "attachments": []},
                    "summary": None,
                    "email_content": {
                        "html": None,
                        "text": None
                    },
                    "processed_at": datetime.now().isoformat(),
                    "handle": email_instructions.handle,
                    "errors": [error_msg],
                    "email_sent": {
                        "status": "error",
                        "timestamp": datetime.now().isoformat(),
                        "error": error_msg
                    }
                }

        except Exception as e:
            error_msg = f"Critical error in email processing: {e!s}"
            logger.error(error_msg, exc_info=True)

            # Ensure we always return a response, even in case of critical failure
            return {
                "attachments": {"summary": None, "attachments": []},
                "summary": None,
                "email_content": {
                    "html": None,
                    "text": None
                },
                "processed_at": datetime.now().isoformat(),
                "handle": email_instructions.handle,
                "errors": [error_msg],
                "email_sent": {
                    "status": "error",
                    "timestamp": datetime.now().isoformat(),
                    "error": error_msg
                }
            }
