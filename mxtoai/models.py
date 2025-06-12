from typing import Any, Optional

from pydantic import BaseModel, model_validator


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


class LiteLLMParams(BaseModel):
    model: str
    weight: int

    # Traditional API-based model parameters (optional for Bedrock models)
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    api_version: Optional[str] = None

    # AWS Bedrock-specific parameters
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_session_token: Optional[str] = None
    aws_region_name: Optional[str] = None
    aws_session_name: Optional[str] = None
    aws_profile_name: Optional[str] = None
    aws_role_name: Optional[str] = None
    aws_web_identity_token: Optional[str] = None
    aws_bedrock_runtime_endpoint: Optional[str] = None
    # Support for Bedrock Application Inference Profile ARNs
    aws_bedrock_inference_profile: Optional[str] = None

class ModelConfig(BaseModel):
    model_name: str
    litellm_params: LiteLLMParams


class RouterConfig(BaseModel):
    routing_strategy: str
    fallbacks: list[dict[str, list[str]]]
    default_litellm_params: dict[str, Any]
