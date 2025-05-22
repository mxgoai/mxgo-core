from mxtoai._logging import get_logger
from mxtoai.email_handles import DEFAULT_EMAIL_HANDLES
from mxtoai.instruction_resolver import ProcessingInstructionsResolver
from mxtoai.models import ProcessingInstructions

# Initialize logger
logger = get_logger(__name__)

# Use DEFAULT_EMAIL_HANDLES as default_instructions
default_instructions = DEFAULT_EMAIL_HANDLES

processing_instructions_resolver = ProcessingInstructionsResolver(DEFAULT_EMAIL_HANDLES)


def get_processing_instructions(handle_name, config):
    try:
        return ProcessingInstructions(**config)
    except KeyError:
        logger.warning(f"Handle '{handle_name}' not found in configuration.")
        # Fallback to a default or raise an error, depending on desired behavior
        # For now, returning a default ProcessingInstructions instance
        return default_instructions
    else:
        return ProcessingInstructions(**config)  # Return from else block
