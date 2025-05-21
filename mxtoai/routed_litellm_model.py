import os
from typing import Any, Optional, List, Dict

import toml
from dotenv import load_dotenv
from smolagents import ChatMessage, LiteLLMRouterModel, Tool

from mxtoai._logging import get_logger
from mxtoai.handle_configuration import EmailHandleInstructions

load_dotenv()

logger = get_logger("routed_litellm_model")


class RoutedLiteLLMModel(LiteLLMRouterModel):
    """LiteLLM Model with routing capabilities, using LiteLLMRouterModel from smolagents."""

    def __init__(self, current_handle: Optional[EmailHandleInstructions] = None, config_path: Optional[str] = "model.config.toml", **kwargs):
        """
        Initialize the routed LiteLLM model.

        Args:
            current_handle: Current email handle configuration being processed
            **kwargs: Additional arguments passed to parent class (e.g., flatten_messages_as_text)

        """
        self.current_handle = current_handle
        self.config_path = config_path
        self.config = self._load_toml_config()

        # Configure model list from environment variables
        model_list = self._load_model_config()
        client_router_kwargs = self._load_router_config()
        
        # The model_id for LiteLLMRouterModel is the default model group the router will target.
        # Our _get_target_model() will override this per call via the 'model' param in generate().
        default_model_group = os.getenv("LITELLM_DEFAULT_MODEL_GROUP")

        if not default_model_group:
            # raise custom exception after exception handling is merged
            raise ValueError("LITELLM_DEFAULT_MODEL_GROUP environment variable is required.")

        super().__init__(
            model_id=default_model_group,
            model_list=model_list,
            client_kwargs=client_router_kwargs,
            **kwargs,  # Pass through other LiteLLMModel/Model kwargs
        )

    def _load_toml_config(self) -> Dict[str, Any]:
        """
        Load configuration from a TOML file.
        
        Returns:    
            Dict[str, Any]: Configuration loaded from the TOML file.
        """

        if not os.path.exists(self.config_path):
            logger.error(f"Model config file not found at {self.config_path}")
            return {}

        try:
            with open(self.config_path, "r") as f:
                return toml.load(f)
        except Exception as e:
            logger.error(f"Failed to load TOML config: {e}")
            return {}

    def _load_model_config(self) -> List[Dict[str, Any]]:
        """
        Load model configuration from environment variables.

        Returns:
            List[Dict[str, Any]]: List of model configurations.

        """
        model_entries = self.config.get("model", [])
        model_list = []

        if isinstance(model_entries, dict):
            # In case there's only one model (TOML parser returns dict)
            model_entries = [model_entries]

        for entry in model_entries:
            model_config = {
                "model_name": entry.get("model_name"),
                "litellm_params": entry.get("litellm_params", {}),
                "weight": entry.get("weight", 1)
            }
            model_list.append(model_config)

        if not model_list:
            logger.warning("No models found in model.config.toml. Using default configuration.")
            model_list = self._get_default_model_list()

        return model_list

    
    def _get_default_model_list(self) -> List[Dict[str, Any]]:
        """
        Provide a default model list as fallback if no environment configuration is found.
        
        Returns:
            List[Dict[str, Any]]: Default model configurations
        """
        return [
            {
                "model_name": "gpt-4",
                "litellm_params": {
                    "model": f"azure/{os.getenv('GPT4O_1_NAME')}",
                    "base_url": os.getenv("GPT4O_1_ENDPOINT"),
                    "api_key": os.getenv("GPT4O_1_API_KEY"),
                    "api_version": os.getenv("GPT4O_1_API_VERSION"),
                    "weight": int(os.getenv("GPT4O_1_WEIGHT", 5)),
                },
            },
            {
                "model_name": "gpt-4",
                "litellm_params": {
                    "model": f"azure/{os.getenv('GPT41_MINI_NAME')}",
                    "base_url": os.getenv("GPT41_MINI_ENDPOINT"),
                    "api_key": os.getenv("GPT41_MINI_API_KEY"),
                    "api_version": os.getenv("GPT41_MINI_API_VERSION"),
                    "weight": int(os.getenv("GPT41_MINI_WEIGHT", 5)),
                },
            },
            {
                "model_name": "gpt-4-reasoning",
                "litellm_params": {
                    "model": f"azure/{os.getenv('O3_MINI_NAME')}",
                    "api_base": os.getenv("O3_MINI_ENDPOINT"),
                    "api_key": os.getenv("O3_MINI_API_KEY"),
                    "api_version": os.getenv("O3_MINI_API_VERSION"),
                    "weight": int(os.getenv("O3_MINI_WEIGHT", 1)),
                },
            },
        ]

    def _load_router_config(self) -> Dict[str, Any]:
        """
        Load router configuration from environment variables.
        
        Returns:
            Dict[str, Any]: Router configuration
        """
        router_config = self.config.get("router_config", {})
        
        if not router_config:
            logger.warning("No router config found in model-config.toml. Using defaults.")
            return {
                "routing_strategy": "simple-shuffle",
                "fallbacks": [{"gpt-4": ["gpt-4-reasoning"]}],
                "default_litellm_params": {"drop_params": True},
            }
        return router_config


    def _get_target_model(self) -> str:
        """
        Determine which model to route to based on the current handle configuration.

        Returns:
            str: The model name (group) to route to.

        """
        if self.current_handle and self.current_handle.target_model:
            logger.debug(
                f"Using model group {self.current_handle.target_model} for handle {self.current_handle.handle}"
            )
            return self.current_handle.target_model

        return "gpt-4"  # Default to gpt-4 model group

    def __call__(
        self,
        messages: list[dict[str, Any]],  # MODIFIED type hint for messages
        stop_sequences: Optional[list[str]] = None,
        grammar: Optional[str] = None,
        tools_to_call_from: Optional[list[Tool]] = None,
        **kwargs,  # kwargs from the caller of this RoutedLiteLLMModel instance
    ) -> ChatMessage:
        try:
            target_model_group = self._get_target_model()

            # Temporarily set self.model_id to the target_model_group for this call.
            # This ensures that when LiteLLMModel.generate calls
            # self._prepare_completion_kwargs(model=self.model_id, ...),
            # it uses our desired target_model_group.
            original_smol_model_id = self.model_id
            self.model_id = target_model_group

            # Remove 'model' from kwargs if present, to prevent conflict with the
            # explicit 'model=self.model_id' passed by LiteLLMModel.generate
            # to _prepare_completion_kwargs.
            kwargs_for_super_generate = {k: v for k, v in kwargs.items() if k != "model"}

            try:
                chat_message = super().generate(
                    messages=messages,
                    stop_sequences=stop_sequences,
                    grammar=grammar,
                    tools_to_call_from=tools_to_call_from,
                    # Do not pass 'model' as an explicit argument here,
                    # as self.model_id is now set to our target_model_group.
                    **kwargs_for_super_generate,
                )
            finally:
                # Restore the original model_id for the instance.
                self.model_id = original_smol_model_id

            return chat_message

        except Exception as e:
            # Log the error and re-raise with more context
            logger.error(f"Error in RoutedLiteLLMModel completion: {e!s}")
            msg = f"Failed to get completion from LiteLLM router: {e!s}"
            raise RuntimeError(msg) from e
