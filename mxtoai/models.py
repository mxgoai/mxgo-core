from typing import Optional

from pydantic import BaseModel


class ProcessingInstructions(BaseModel):
    handle: str
    aliases: list[str]
    process_attachments: bool
    deep_research_mandatory: bool
    rejection_message: Optional[str] = (
        "This email handle is not supported. Please visit https://mxtoai.com/docs/email-handles to learn about supported email handles."
    )
    task_template: Optional[str] = None
    output_template: Optional[str] = None
    task_specific_instructions: Optional[str] = None
    requires_language_detection: bool = False
    requires_schedule_extraction: bool = False
    target_model: Optional[str] = "gpt-4"
    output_instructions: Optional[str] = None
