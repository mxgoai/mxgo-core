from typing import Optional

from pydantic import BaseModel

from mxtoai.prompts import (
    template_prompts,
    output_prompts
)

class EmailHandleInstructions(BaseModel):
    handle: str
    aliases: list[str]
    process_attachments: bool
    deep_research_mandatory: bool
    rejection_message: Optional[str] = "This email handle is not supported. Please visit https://mxtoai.com/docs/email-handles to learn about supported email handles."
    task_template: Optional[str] = None
    requires_language_detection: bool = False  # Specifically for translate handle
    requires_schedule_extraction: bool = False  # Specifically for schedule handle
    target_model: Optional[str] = "gpt-4"  # Default to gpt-4, can be overridden per handle
    output_template: Optional[str] = None  # Template for structuring the output


# Define all email handle configurations
EMAIL_HANDLES = [
    EmailHandleInstructions(
        handle="summarize",
        aliases=["summarise", "summary"],
        process_attachments=True,
        deep_research_mandatory=False,
        target_model="gpt-4",
        task_template=template_prompts.SUMMARIZE_TEMPLATE,
        output_template=output_prompts.SUMMARIZE_OUTPUT_GUIDELINES,
    ),
    EmailHandleInstructions(
        handle="research",
        aliases=["deep-research"],
        process_attachments=True,
        deep_research_mandatory=True,
        add_summary=True,
        target_model="gpt-4-reasoning",
        task_template=template_prompts.RESEARCH_TEMPLATE,
        output_template=output_prompts.RESEARCH_OUTPUT_GUIDELINES,
    ),
    EmailHandleInstructions(
        handle="simplify",
        aliases=["eli5", "explain"],
        process_attachments=True,
        deep_research_mandatory=False,
        target_model="gpt-4",
        task_template=template_prompts.SIMPLIFY_TEMPLATE,
        output_template=output_prompts.SIMPLIFY_OUTPUT_GUIDELINES,
    ),
    EmailHandleInstructions(
        handle="ask",
        aliases=["custom", "agent", "assist", "assistant", "hi", "hello", "question"],
        process_attachments=True,
        deep_research_mandatory=False,
        target_model="gpt-4",
        task_template=template_prompts.ASK_TEMPLATE,
        output_template=output_prompts.ASK_OUTPUT_GUIDELINES,
    ),
    EmailHandleInstructions(
        handle="fact-check",
        aliases=["factcheck", "verify"],
        process_attachments=True,
        deep_research_mandatory=False,
        target_model="gpt-4-reasoning",
        task_template=template_prompts.FACT_TEMPLATE,
        output_template=output_prompts.FACT_CHECK_OUTPUT_GUIDELINES,
    ),
    EmailHandleInstructions(
        handle="background-research",
        aliases=["background-check", "background"],
        process_attachments=True,
        deep_research_mandatory=False,
        target_model="gpt-4-reasoning",
        task_template=template_prompts.BACKGROUND_RESEARCH_TEMPLATE,
        output_template=output_prompts.BACKGROUND_OUTPUT_GUIDELINES,
    ),
    EmailHandleInstructions(
        handle="translate",
        aliases=["translation"],
        process_attachments=True,
        deep_research_mandatory=False,
        target_model="gpt-4",
        task_template=template_prompts.TRANSLATE_TEMPLATE,
        output_template=output_prompts.TRANSLATION_OUTPUT_GUIDELINES,
    ),
    EmailHandleInstructions(
        handle="schedule",
        aliases=["schedule-action"],
        process_attachments=True,
        deep_research_mandatory=False,
        target_model="gpt-4",
        requires_schedule_extraction=True,
        task_template=template_prompts.SCHEDULE_TEMPLATE,
        output_template=output_prompts.SCHEDULE_OUTPUT_GUIDELINES,
    ),
]

# Create a mapping of handles (including aliases) to their configurations
HANDLE_MAP = {}
for config in EMAIL_HANDLES:
    HANDLE_MAP[config.handle] = config
    for alias in config.aliases:
        HANDLE_MAP[alias] = config
