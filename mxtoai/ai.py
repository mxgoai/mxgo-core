import asyncio
import json
import os
from typing import Any, Optional

from _logging import get_logger
from dotenv import load_dotenv
from litellm import acompletion

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger("ai")

# Enable preview features for Azure O-series models
import contextlib

import litellm

litellm.enable_preview_features = True


def _try_extract_from_choice_message_content(choice: Any, logger_instance: Any) -> Optional[str]:
    """Tries to extract content from choice.message.content structure."""
    if hasattr(choice, "message") and hasattr(choice.message, "content"):
        content = choice.message.content
        if content:
            logger_instance.info("Extracted content via choice.message.content attribute")
            return str(content)
    # Try dictionary access if object access failed for message.content
    if isinstance(choice, dict) and "message" in choice and isinstance(choice["message"], dict):
        content = choice["message"].get("content")
        if content:
            logger_instance.info("Extracted content via choice['message']['content'] dict access")
            return str(content)
    return None

def _try_extract_from_choice_text(choice: Any, logger_instance: Any) -> Optional[str]:
    """Tries to extract content from choice.text structure."""
    if hasattr(choice, "text"):
        content = choice.text
        if content:
            logger_instance.info("Extracted content via choice.text attribute")
            return str(content)
    # Try dictionary access if object access failed for text
    if isinstance(choice, dict) and "text" in choice:
        content = choice["text"]
        if content:
            logger_instance.info("Extracted content via choice['text'] dict access")
            return str(content)
    return None

def _extract_content_from_llm_response(response: Any, logger_instance: Any) -> Optional[str]:
    """Helper function to extract content from various LLM response formats."""
    # Attempt 1: Direct attribute access (common for many SDKs)
    if (
        hasattr(response, "choices")
        and response.choices
        and isinstance(response.choices, list)
        and len(response.choices) > 0
    ):
        first_choice = response.choices[0]
        content = _try_extract_from_choice_message_content(first_choice, logger_instance)
        if content:
            return content
        content = _try_extract_from_choice_text(first_choice, logger_instance)
        if content:
            return content

    # Attempt 2: Dictionary access (common for raw API responses or some SDKs)
    response_dict = {}
    if hasattr(response, "__dict__"):
        response_dict = response.__dict__
    elif isinstance(response, dict):
        response_dict = response

    if response_dict.get("choices") and isinstance(response_dict["choices"], list) and len(response_dict["choices"]) > 0:
        first_choice_dict = response_dict["choices"][0]
        # Pass the dictionary form of the choice to helper
        content = _try_extract_from_choice_message_content(first_choice_dict, logger_instance)
        if content:
            return content
        content = _try_extract_from_choice_text(first_choice_dict, logger_instance)
        if content:
            return content

    logger_instance.warning("Could not extract content using known patterns.")
    return None


async def ask_llm(prompt: str, email_data: dict[str, Any], model: Optional[str] = None) -> str:
    """
    Process an email using LiteLLM to generate a response.

    Args:
        prompt: The prompt to send to the LLM
        email_data: JSON format of the email data
        model: The model to use for completion (default: None, will use Azure OpenAI)

    Returns:
        The LLM response as a string

    """
    try:
        # Use Azure OpenAI model if no model is specified
        if model is None:
            # Use the Azure OpenAI model specified in the environment variables
            model = f"azure/{os.getenv('AZURE_OPENAI_MODEL', 'o3-mini-deep-research')}"
            logger.info(f"Using Azure OpenAI model: {model}")

        # Format the email data as part of the prompt
        email_json = json.dumps(email_data, indent=2)
        full_prompt = f"{prompt}\n\nEmail Data:\n{email_json}"

        logger.info(f"Sending request to LLM model: {model}")
        logger.debug(f"Email subject: {email_data.get('subject', 'N/A')}")

        # Print environment variables for debugging (without the actual API key)
        logger.info(f"AZURE_OPENAI_MODEL: {os.getenv('AZURE_OPENAI_MODEL')}")
        logger.info(f"AZURE_OPENAI_ENDPOINT: {os.getenv('AZURE_OPENAI_ENDPOINT')}")
        logger.info(f"API Key present: {bool(os.getenv('AZURE_OPENAI_API_KEY'))}")
        logger.info(f"AZURE_OPENAI_API_VERSION: {os.getenv('AZURE_OPENAI_API_VERSION')}")

        try:
            # Call the LLM using litellm's async completion with Azure OpenAI configuration
            response = await acompletion(
                model=model,
                messages=[{"role": "user", "content": full_prompt}],
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_base=os.getenv("AZURE_OPENAI_ENDPOINT"),
                api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
            )

            # Print the raw response for debugging
            logger.info(f"Raw response type: {type(response)}")
            logger.info(f"Raw response: {response}")

            content = _extract_content_from_llm_response(response, logger)

        except Exception as azure_error:
            logger.exception("Error processing LLM response")
            # Fallback to a generic error message if specific error handling fails
            return f"Error: Could not process response from LLM. Details: {azure_error!s}"
        else:
            if content:
                return content
            logger.warning("Could not extract content from LLM response after acompletion success")
            return "Error: Failed to extract a meaningful response from the LLM (after successful acompletion)."

    except Exception as e:
        # Log the error and return an error message
        error_msg = f"Error processing with LLM: {e!s}"
        logger.exception("Error processing with LLM")
        return error_msg


# Test function for the ask_llm method
async def test_ask_llm():
    """
    Test the ask_llm function with a sample email.
    """
    # Sample email data
    sample_email = {
        "from": "user@example.com",
        "to": "ai-assistant@mxtoai.com",
        "subject": "Meeting Request",
        "body": "Hi there,\n\nI'd like to schedule a meeting next week to discuss the project. Are you available on Tuesday at 2 PM?\n\nBest regards,\nJohn",
    }

    # Sample prompt
    prompt = "Summarize this email and identify any action items."

    # Call the ask_llm function
    await ask_llm(prompt, sample_email)


# Alternative test with OpenAI model as fallback
async def test_with_openai_fallback():
    """
    Test the ask_llm function with OpenAI as a fallback.
    """
    # Sample email data
    sample_email = {
        "from": "user@example.com",
        "to": "ai-assistant@mxtoai.com",
        "subject": "Meeting Request",
        "body": "Hi there,\n\nI'd like to schedule a meeting next week to discuss the project. Are you available on Tuesday at 2 PM?\n\nBest regards,\nJohn",
    }

    # Sample prompt
    prompt = "Summarize this email and identify any action items."

    # Try with OpenAI model
    with contextlib.suppress(Exception):
        await ask_llm(prompt, sample_email, model="gpt-3.5-turbo")


# Run the test function if this file is executed directly
if __name__ == "__main__":
    # Make sure environment variables are loaded
    load_dotenv()

    # Run the Azure test
    asyncio.run(test_ask_llm())

    # Uncomment to test with OpenAI fallback if Azure fails
    asyncio.run(test_with_openai_fallback())
