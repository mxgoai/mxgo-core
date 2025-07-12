from datetime import datetime, timezone

from mxtoai._logging import get_logger
from mxtoai.agents.agent import BaseAgent
from mxtoai.prompts.base_prompts import (
    MARKDOWN_STYLE_GUIDE,
    RESEARCH_GUIDELINES,
    RESPONSE_GUIDELINES,
    SECURITY_GUIDELINES,
)
from mxtoai.prompts.template_prompts import (
    SCHEDULED_TASK_DISTILLED_INSTRUCTIONS_TEMPLATE,
)
from mxtoai.routed_litellm_model import RoutedLiteLLMModel
from mxtoai.schemas import (
    AgentResearchMetadata,
    AgentResearchOutput,
    DetailedEmailProcessingResult,
    EmailContentDetails,
    EmailRequest,
    EmailSentStatus,
    ProcessingError,
    ProcessingInstructions,
    ProcessingMetadata,
    AttachmentsProcessingResult,
)
from mxtoai import exceptions
from smolagents import LiteLLMModel
import tomllib
import os

logger = get_logger("research_agent")


class ResearchAgent(BaseAgent):
    """
    Research agent that performs direct model research on email requests.
    
    Unlike EmailAgent which uses tools and multi-step processing, ResearchAgent 
    calls the routed model directly with initial prompts for streamlined research tasks.
    The routing system still applies based on the handle's target_model configuration.
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
        Initialize the research agent.

        Args:
            email_request: The email request to process
            processing_instructions: Instructions defining processing configuration
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

        # Initialize the routed model for direct research calls
        self.routed_model = RoutedLiteLLMModel()
        
        logger.info("Research agent initialized successfully")

    def _extract_and_log_token_usage(self, response) -> dict:
        """Extract token usage from response and log it."""
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        try:
            if hasattr(response, 'usage') and response.usage:
                usage["prompt_tokens"] = getattr(response.usage, 'prompt_tokens', 0)
                usage["completion_tokens"] = getattr(response.usage, 'completion_tokens', 0)
                usage["total_tokens"] = getattr(response.usage, 'total_tokens', 0)
            elif hasattr(response, 'raw') and response.raw and hasattr(response.raw, 'usage'):
                raw_usage = response.raw.usage
                usage["prompt_tokens"] = getattr(raw_usage, 'prompt_tokens', 0)
                usage["completion_tokens"] = getattr(raw_usage, 'completion_tokens', 0)
                usage["total_tokens"] = getattr(raw_usage, 'total_tokens', 0)
            
            # Calculate total if not provided
            if usage["total_tokens"] == 0 and (usage["prompt_tokens"] > 0 or usage["completion_tokens"] > 0):
                usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
                
            # Log the usage
            logger.info(f"🔢 Research call completed - Token usage: {usage['prompt_tokens']} prompt + {usage['completion_tokens']} completion = {usage['total_tokens']} total")
            
        except Exception as e:
            logger.warning(f"Failed to extract token usage: {e}")
            
        return usage

    def _load_model_config(self):
        """
        Load the model configuration from the environment variable or default path.
        
        Returns:
            dict: The model configuration dictionary
        """
        # Load model config
        config_path = os.getenv("LITELLM_CONFIG_PATH", "model.config.toml")
        with open(config_path, "rb") as f:
            config = tomllib.load(f)
        deep_research_model = None
        for entry in config.get("model", []):
            if entry.get("model_name") == "deep-research":
                deep_research_model = entry["litellm_params"]
                break
        if not deep_research_model:
            raise exceptions.DeepResearchModelNotFoundError("No 'deep-research' model found in model.config.toml")

        # Set Azure env vars for compatibility (if needed)
        if deep_research_model.get("api_key"):
            os.environ["AZURE_OPENAI_API_KEY"] = deep_research_model["api_key"]
        if deep_research_model.get("base_url"):
            os.environ["AZURE_OPENAI_ENDPOINT"] = deep_research_model["base_url"]
        if deep_research_model.get("api_version"):
            os.environ["AZURE_OPENAI_API_VERSION"] = deep_research_model["api_version"]

        # Instantiate LiteLLMModel directly
        self.model = LiteLLMModel(
            model_id=deep_research_model["model"],
            api_base=deep_research_model.get("base_url"),
            api_key=deep_research_model.get("api_key"),
            api_version=deep_research_model.get("api_version"),
        )
    
    def process_email(
        self,
        email_request: EmailRequest,
        email_instructions: ProcessingInstructions,
    ) -> DetailedEmailProcessingResult:
        """
        Process an email using direct model call to the deep-research model (no routing).
        """
        try:
            self._load_model_config()  # Load model configuration

            research_prompt = self._create_research_prompt(email_request, email_instructions)
            logger.info("Starting direct deep-research model call (no routing)...")
            
            # Make the model call
            response = self.model([
                {"role": "user", "content": research_prompt}
            ])
            
            # Extract and log token usage
            token_usage = self._extract_and_log_token_usage(response)
            
            research_content = response.content if hasattr(response, 'content') else str(response)
            logger.info("Direct deep-research model call completed")

            finalized_content = self._finalize_response_with_citations(research_content)
            email_text_content = self.report_formatter.format_report(
                finalized_content, format_type="text", include_signature=True
            )
            email_html_content = self.report_formatter.format_report(
                finalized_content, format_type="html", include_signature=True
            )
            
            processed_at_time = datetime.now(timezone.utc).isoformat()
            return DetailedEmailProcessingResult(
                metadata=ProcessingMetadata(
                    processed_at=processed_at_time,
                    mode=email_instructions.handle,
                    errors=[],
                    email_sent=EmailSentStatus(status="success", timestamp=processed_at_time),
                ),
                email_content=EmailContentDetails(
                    text=email_text_content,
                    html=email_html_content,
                    enhanced={"text": email_text_content, "html": email_html_content},
                ),
                attachments=AttachmentsProcessingResult(processed=[]),
                calendar_data=None,
                research=AgentResearchOutput(
                    findings_content=finalized_content,
                    metadata=AgentResearchMetadata(
                        query=f"Direct research for email: {email_request.subject}",
                        annotations=[],
                        visited_urls=[],
                        read_urls=[],
                        timestamp=processed_at_time,
                        usage=token_usage,  # Include token usage in metadata
                        num_urls=0,
                    )
                ),
                pdf_export=None,
            )
        except Exception as e:
            error_msg = f"Critical error in research processing: {e!s}"
            logger.exception(error_msg)
            
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
                        "I encountered a critical error processing your research request.",
                        format_type="text",
                        include_signature=True,
                    ),
                    html=self.report_formatter.format_report(
                        "I encountered a critical error processing your research request.",
                        format_type="html",
                        include_signature=True,
                    ),
                    enhanced={"text": None, "html": None},
                ),
                attachments=AttachmentsProcessingResult(processed=[]),
                calendar_data=None,
                research=AgentResearchOutput(
                    findings_content=None,
                    metadata=AgentResearchMetadata(
                        query=f"Research error for email: {email_request.subject if email_request else 'unknown'}",
                        annotations=[],
                        visited_urls=[],
                        read_urls=[],
                        timestamp=now_iso,
                        usage={},  # Empty usage data for error case
                        num_urls=0,
                    )
                ) if email_request else None,
                pdf_export=None,
            )

    def _create_research_prompt(
        self,
        email_request: EmailRequest,
        email_instructions: ProcessingInstructions,
        attachment_task: str = ""
    ) -> str:
        """
        Create a research-focused prompt for direct model processing.

        Args:
            email_request: EmailRequest instance containing email data
            email_instructions: ProcessingInstructions object containing processing configuration

        Returns:
            str: The research prompt for direct model call
        """
        # Create basic email context
        email_context = self._create_email_context(email_request)
        
        # Create distilled processing instructions section for scheduled tasks
        distilled_section = ""
        if email_request.distilled_processing_instructions:
            distilled_section = SCHEDULED_TASK_DISTILLED_INSTRUCTIONS_TEMPLATE.format(
                distilled_processing_instructions=email_request.distilled_processing_instructions
            )
        
        # Build comprehensive research prompt
        sections = [
            f"Process this email according to the '{email_instructions.handle}' instruction type for DIRECT RESEARCH.\n",
            email_context,
            distilled_section,
            RESEARCH_GUIDELINES["mandatory"],
            attachment_task,
            email_instructions.task_template if email_instructions.task_template else "",
            email_instructions.output_template if email_instructions.output_template else "",
            RESPONSE_GUIDELINES,
            MARKDOWN_STYLE_GUIDE,
            SECURITY_GUIDELINES,
        ]

        return "\n\n".join(filter(None, sections))
    