import os
from typing import Optional

from dotenv import load_dotenv
from litellm import Router
from smolagents import ChatMessage, LiteLLMModel, Tool

from mxtoai._logging import get_logger
from mxtoai.handle_configuration import EmailHandleInstructions

load_dotenv()

logger = get_logger("routed_litellm_model")

class RoutedLiteLLMModel(LiteLLMModel):
    """LiteLLM Model with routing capabilities"""

    def __init__(self, current_handle: Optional[EmailHandleInstructions] = None, **kwargs):
        """
        Initialize the routed LiteLLM model.

        Args:
            current_handle: Current email handle configuration being processed
            **kwargs: Additional arguments passed to parent class

        """
        super().__init__(model_id="gpt-4", **kwargs)

        self.current_handle = current_handle

        # Configure model list from environment variables
        model_list = [
            {
                "model_name": "gpt-4",
                "litellm_params": {
                    "model": f"azure/{os.getenv('GPT4O_1_NAME')}",
                    "api_base": os.getenv("GPT4O_1_ENDPOINT"),
                    "api_key": os.getenv("GPT4O_1_API_KEY"),
                    "api_version": os.getenv("GPT4O_1_API_VERSION"),
                    "weight": int(os.getenv("GPT4O_1_WEIGHT", 5)),
                    "drop_params": True  # Enable dropping of unsupported parameters
                }
            },
            {
                "model_name": "gpt-4",
                "litellm_params": {
                    "model": f"azure/{os.getenv('GPT4O_2_NAME')}",
                    "api_base": os.getenv("GPT4O_2_ENDPOINT"),
                    "api_key": os.getenv("GPT4O_2_API_KEY"),
                    "api_version": os.getenv("GPT4O_2_API_VERSION"),
                    "weight": int(os.getenv("GPT4O_2_WEIGHT", 5)),
                    "drop_params": True  # Enable dropping of unsupported parameters
                }
            },
            {
                "model_name": "gpt-4-reasoning",
                "litellm_params": {
                    "model": f"azure/{os.getenv('O3_MINI_NAME')}",
                    "api_base": os.getenv("O3_MINI_ENDPOINT"),
                    "api_key": os.getenv("O3_MINI_API_KEY"),
                    "api_version": os.getenv("O3_MINI_API_VERSION"),
                    "weight": int(os.getenv("O3_MINI_WEIGHT", 1)),
                    "drop_params": True  # Enable dropping of unsupported parameters
                }
            }
        ]

        # Initialize router with settings
        self.router = Router(
            model_list=model_list,
            routing_strategy="simple-shuffle",
            fallbacks=[{
                "gpt-4": ["gpt-4-reasoning"]  # Fallback to reasoning model if both GPT-4 instances fail
            }],
            default_litellm_params={"drop_params": True}  # Global setting for dropping unsupported parameters
        )

    def _get_target_model(self) -> str:
        """
        Determine which model to route to based on the current handle configuration.

        Returns:
            str: The model name to route to

        """
        if self.current_handle and self.current_handle.target_model:
            logger.debug(f"Using model {self.current_handle.target_model} for handle {self.current_handle.handle}")
            return self.current_handle.target_model

        return "gpt-4"  # Default to gpt-4 if no handle specified or no target model set

    def __call__(
        self,
        messages: list[dict[str, str]],
        stop_sequences: Optional[list[str]] = None,
        grammar: Optional[str] = None,
        tools_to_call_from: Optional[list[Tool]] = None,
        **kwargs
    ) -> ChatMessage:
        try:
            completion_kwargs = self._prepare_completion_kwargs(
                messages=messages,
                stop_sequences=stop_sequences,
                grammar=grammar,
                tools_to_call_from=tools_to_call_from,
                **kwargs
            )

            # Determine which model to route to based on handle configuration
            target_model = self._get_target_model()
            completion_kwargs["model"] = target_model

            # Use router for completion
            response = self.router.completion(**completion_kwargs)

            # Update token counts
            self.last_input_token_count = response.usage.prompt_tokens
            self.last_output_token_count = response.usage.completion_tokens

            # Convert to ChatMessage
            first_message = ChatMessage.from_dict(
                response.choices[0].message.model_dump(include={"role", "content", "tool_calls"})
            )
            return self.postprocess_message(first_message, tools_to_call_from)

        except Exception as e:
            # Log the error and re-raise with more context
            logger.error(f"Error in RoutedLiteLLMModel completion: {e!s}")
            msg = f"Failed to get completion from LiteLLM router: {e!s}"
            raise RuntimeError(msg) from e
