"""
External Data Module for MXtoAI.

This module provides integration with various external data sources to enhance
the capabilities of the MXtoAI email agent.
"""

from .linkedin import (
    LinkedInDataAPITool,
    LinkedInFreshDataTool,
    initialize_linkedin_data_api_tool,
    initialize_linkedin_fresh_tool,
)

__all__ = [
    "LinkedInDataAPITool",
    "LinkedInFreshDataTool",
    "initialize_linkedin_data_api_tool",
    "initialize_linkedin_fresh_tool",
]

# Version of the external data module
__version__ = '0.2.0'