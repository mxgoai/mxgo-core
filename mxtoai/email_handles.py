from mxtoai.prompts import output_prompts, template_prompts
from mxtoai.schemas import HandlerAlias, ProcessingInstructions, ToolName

# Common tools available to most handles
COMMON_TOOLS = [
    ToolName.ATTACHMENT_PROCESSOR,
    ToolName.CITATION_AWARE_VISIT,
    ToolName.PYTHON_INTERPRETER,
    ToolName.REFERENCES_GENERATOR,
    ToolName.AZURE_VISUALIZER,
    ToolName.PDF_EXPORT,
]

# Search tools for handles that need enhanced search capabilities
SEARCH_TOOLS = [
    ToolName.WEB_SEARCH,  # Fallback search tool with robust error handling
    ToolName.WIKIPEDIA_SEARCH,
    ToolName.GOOGLE_SEARCH,  # Keep for specialized Google search needs
]

# Research tools for handles that need deep research capabilities
RESEARCH_TOOLS = [
    ToolName.DEEP_RESEARCH,
    ToolName.LINKEDIN_FRESH_DATA,
    ToolName.LINKEDIN_DATA_API,
]

# default email handles for processing instructions
DEFAULT_EMAIL_HANDLES = [
    ProcessingInstructions(
        handle=HandlerAlias.SUMMARIZE.value,
        aliases=["summarise", "summary"],
        process_attachments=True,
        deep_research_mandatory=False,
        allowed_tools=COMMON_TOOLS + SEARCH_TOOLS,
        target_model="gpt-4",
        task_template=template_prompts.SUMMARIZE_TEMPLATE,
        output_template=output_prompts.SUMMARIZE_OUTPUT_GUIDELINES,
    ),
    ProcessingInstructions(
        handle=HandlerAlias.RESEARCH.value,
        aliases=["deep-research"],
        process_attachments=True,
        deep_research_mandatory=True,
        allowed_tools=COMMON_TOOLS + SEARCH_TOOLS + RESEARCH_TOOLS,
        add_summary=True,
        target_model="gpt-4",
        task_template=template_prompts.RESEARCH_TEMPLATE,
        output_template=output_prompts.RESEARCH_OUTPUT_GUIDELINES,
    ),
    ProcessingInstructions(
        handle=HandlerAlias.SIMPLIFY.value,
        aliases=["eli5", "explain"],
        process_attachments=True,
        deep_research_mandatory=False,
        allowed_tools=COMMON_TOOLS + SEARCH_TOOLS,
        target_model="gpt-4",
        task_template=template_prompts.SIMPLIFY_TEMPLATE,
        output_template=output_prompts.SIMPLIFY_OUTPUT_GUIDELINES,
    ),
    ProcessingInstructions(
        handle=HandlerAlias.ASK.value,
        aliases=["custom", "agent", "assist", "assistant", "hi", "hello", "question"],
        process_attachments=True,
        deep_research_mandatory=False,
        allowed_tools=COMMON_TOOLS
        + SEARCH_TOOLS
        + RESEARCH_TOOLS
        + [ToolName.MEETING_CREATOR, ToolName.SCHEDULED_TASKS],
        target_model="gpt-4",
        task_template=template_prompts.ASK_TEMPLATE,
        output_template=output_prompts.ASK_OUTPUT_GUIDELINES,
    ),
    ProcessingInstructions(
        handle=HandlerAlias.FACT_CHECK.value,
        aliases=["factcheck", "verify"],
        process_attachments=True,
        deep_research_mandatory=False,
        allowed_tools=COMMON_TOOLS + SEARCH_TOOLS + RESEARCH_TOOLS,
        target_model="gpt-4",
        task_template=template_prompts.FACT_TEMPLATE,
        output_template=output_prompts.FACT_CHECK_OUTPUT_GUIDELINES,
    ),
    ProcessingInstructions(
        handle=HandlerAlias.BACKGROUND_RESEARCH.value,
        aliases=["background-check", "background"],
        process_attachments=True,
        deep_research_mandatory=False,
        allowed_tools=COMMON_TOOLS + SEARCH_TOOLS + RESEARCH_TOOLS,
        target_model="gpt-4",
        task_template=template_prompts.BACKGROUND_RESEARCH_TEMPLATE,
        output_template=output_prompts.BACKGROUND_OUTPUT_GUIDELINES,
    ),
    ProcessingInstructions(
        handle=HandlerAlias.TRANSLATE.value,
        aliases=["translation"],
        process_attachments=True,
        deep_research_mandatory=False,
        allowed_tools=COMMON_TOOLS + SEARCH_TOOLS,
        target_model="gpt-4",
        task_template=template_prompts.TRANSLATE_TEMPLATE,
        output_template=output_prompts.TRANSLATION_OUTPUT_GUIDELINES,
    ),
    ProcessingInstructions(
        handle=HandlerAlias.MEETING.value,
        aliases=["meet", "find-time", "calendar"],
        process_attachments=True,
        deep_research_mandatory=False,
        allowed_tools=[*COMMON_TOOLS, ToolName.MEETING_CREATOR],
        target_model="gpt-4",
        requires_schedule_extraction=True,
        task_template=template_prompts.MEETING_TEMPLATE,
        output_template=output_prompts.MEETING_OUTPUT_GUIDELINES,
    ),
    ProcessingInstructions(
        handle=HandlerAlias.PDF.value,
        aliases=["export", "convert", "document", "export-pdf"],
        process_attachments=True,
        deep_research_mandatory=False,
        allowed_tools=COMMON_TOOLS,
        target_model="gpt-4",
        task_template=template_prompts.PDF_EXPORT_TEMPLATE,
        output_template=output_prompts.PDF_EXPORT_OUTPUT_GUIDELINES,
    ),
    ProcessingInstructions(
        handle=HandlerAlias.SCHEDULE.value,
        aliases=[
            "remind",
            "recurring",
            "schedule-task",
            "schedule-reminder",
            "future-task",
            "recurring-task",
            "delayed-processing",
        ],
        process_attachments=True,
        deep_research_mandatory=False,
        allowed_tools=[*COMMON_TOOLS, ToolName.SCHEDULED_TASKS],
        target_model="gpt-4",
        task_template=template_prompts.FUTURE_TEMPLATE,
        output_template=output_prompts.FUTURE_OUTPUT_GUIDELINES,
    ),
    ProcessingInstructions(
        handle=HandlerAlias.DELETE.value,
        aliases=[
            "cancel",
            "cancel-task",
            "delete-task",
            "remove-task",
            "unschedule",
            "stop-task",
        ],
        process_attachments=False,
        deep_research_mandatory=False,
        allowed_tools=[
            ToolName.DELETE_SCHEDULED_TASKS,
            ToolName.PYTHON_INTERPRETER,
            ToolName.REFERENCES_GENERATOR,
        ],
        target_model="gpt-4",
        task_template=template_prompts.DELETE_TEMPLATE,
        output_template=output_prompts.DELETE_OUTPUT_GUIDELINES,
    ),
]
