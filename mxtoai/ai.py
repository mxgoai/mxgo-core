"""
AI interaction module for mxtoai package.

This module handles communication with AI models for email processing.
"""
import logging
import asyncio
from typing import Dict, Any, Optional

# Setup logging
logger = logging.getLogger(__name__)

async def ask_llm(prompt: str, email_data: Dict[str, Any], max_retries: int = 3) -> str:
    """
    Ask the language model to process an email based on a prompt.
    
    Args:
        prompt: The instruction for the AI (e.g., "Summarize this email")
        email_data: Dictionary containing email data
        max_retries: Maximum number of retries if API call fails
        
    Returns:
        str: The AI-generated response
    """
    try:
        # Log the request
        logger.info(f"Processing AI request with prompt: {prompt}")
        
        # Default response in case we can't reach the AI service
        default_response = "This email contains text"
        
        # Extract some basic info we can use in the default response
        subject = email_data.get('subject', '')
        has_attachments = len(email_data.get('processed_attachments', [])) > 0
        
        # Create a more informative default response
        if subject:
            default_response = f"This email with subject '{subject}'"
            if has_attachments:
                attachment_count = len(email_data.get('processed_attachments', []))
                default_response += f" contains {attachment_count} attachment(s)"
        
        # TODO: Implement actual AI model integration here
        # For now, return a default summary to let testing continue
        logger.warning("Using default AI response as no AI model is configured")
        
        # Simulate a small delay like a real API call would have
        await asyncio.sleep(0.5)
        
        # Return the default response
        return default_response
        
    except Exception as e:
        logger.error(f"Error in ask_llm: {str(e)}")
        return "Unable to process this email due to an error." 