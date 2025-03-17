from litellm import acompletion
import json
import os
import asyncio
from typing import Dict, Any, Optional, cast
from _logging import get_logger
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize logger
logger = get_logger("ai")

# Enable preview features for Azure O-series models
import litellm
litellm.enable_preview_features = True


async def ask_llm(prompt: str, email_data: Dict[str, Any], model: Optional[str] = None) -> str:
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
                api_version=os.getenv("AZURE_OPENAI_API_VERSION")
            )
            
            # Print the raw response for debugging
            logger.info(f"Raw response type: {type(response)}")
            logger.info(f"Raw response: {response}")
            
            # Direct access to response.choices[0].message.content
            # This is the most reliable way to extract content from ModelResponse
            if hasattr(response, 'choices') and response.choices:
                if hasattr(response.choices[0], 'message') and hasattr(response.choices[0].message, 'content'):
                    content = response.choices[0].message.content
                    if content:
                        logger.info("Successfully extracted content directly from response object")
                        return content
            
            # If direct access failed, try dictionary approach
            response_dict = {}
            if hasattr(response, '__dict__'):
                response_dict = response.__dict__
            elif isinstance(response, dict):
                response_dict = response
                
            logger.info(f"Response dict keys: {list(response_dict.keys()) if response_dict else 'None'}")
            
            # Try to extract content from the dictionary
            if 'choices' in response_dict and response_dict['choices']:
                choices = response_dict['choices']
                if isinstance(choices, list) and len(choices) > 0:
                    first_choice = choices[0]
                    logger.debug(f"First choice: {first_choice}")
                    
                    # Try to access message.content
                    if hasattr(first_choice, 'message') and hasattr(first_choice.message, 'content'):
                        content = first_choice.message.content
                        if content:
                            logger.info("Successfully extracted content from choices[0].message.content")
                            return content
                    
                    # Try dictionary access if object access failed
                    if isinstance(first_choice, dict):
                        if 'message' in first_choice and isinstance(first_choice['message'], dict):
                            content = first_choice['message'].get('content')
                            if content:
                                logger.info("Successfully extracted content from dictionary")
                                return content
                        elif 'text' in first_choice:
                            content = first_choice['text']
                            if content:
                                logger.info("Successfully extracted content from text field")
                                return content
            
            # If all extraction methods failed
            logger.warning("Could not extract content from LLM response")
            return "No response generated from LLM."
            
        except Exception as azure_error:
            # Log the Azure error
            logger.warning(f"Azure OpenAI error: {str(azure_error)}")
            return f"Error with Azure OpenAI: {str(azure_error)}"
            
    except Exception as e:
        # Log the error and return an error message
        error_msg = f"Error processing with LLM: {str(e)}"
        logger.error(error_msg)
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
        "body": "Hi there,\n\nI'd like to schedule a meeting next week to discuss the project. Are you available on Tuesday at 2 PM?\n\nBest regards,\nJohn"
    }
    
    # Sample prompt
    prompt = "Summarize this email and identify any action items."
    
    print("Testing ask_llm function...")
    print(f"Prompt: {prompt}")
    print(f"Email: {json.dumps(sample_email, indent=2)}")
    
    # Call the ask_llm function
    response = await ask_llm(prompt, sample_email)
    
    print("\nResponse from LLM:")
    print(response)


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
        "body": "Hi there,\n\nI'd like to schedule a meeting next week to discuss the project. Are you available on Tuesday at 2 PM?\n\nBest regards,\nJohn"
    }
    
    # Sample prompt
    prompt = "Summarize this email and identify any action items."
    
    print("Testing with OpenAI fallback...")
    print(f"Prompt: {prompt}")
    print(f"Email: {json.dumps(sample_email, indent=2)}")
    
    # Try with OpenAI model
    try:
        response = await ask_llm(prompt, sample_email, model="gpt-3.5-turbo")
        
        print("\nResponse from OpenAI:")
        print(response)
    except Exception as e:
        print(f"Error with OpenAI fallback: {str(e)}")


# Run the test function if this file is executed directly
if __name__ == "__main__":
    # Make sure environment variables are loaded
    load_dotenv()
    
    # Run the Azure test
    print("\n=== Testing with Azure OpenAI ===\n")
    asyncio.run(test_ask_llm())
    
    # Uncomment to test with OpenAI fallback if Azure fails
    print("\n=== Testing with OpenAI Fallback ===\n")
    asyncio.run(test_with_openai_fallback())
