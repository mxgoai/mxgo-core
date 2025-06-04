"""
Custom MCP (Model Context Protocol) client implementation for mxtoai.

This module provides a synchronous MCP client that works with smolagents and dramatiq workers.
It replaces the dependency on MCPAdapt library with a custom implementation.
"""

from .client import (
    BaseMCPClient,
    StdioMCPClient, 
    SSEMCPClient,
    MCPClientError,
    MCPConnectionError,
    MCPToolExecutionError,
    create_mcp_client
)

from .tool_adapter import (
    MCPToolAdapter,
    sanitize_function_name,
    create_smolagents_tools_from_mcp_client
)

from .tool_collection import (
    CustomMCPToolCollection,
    load_mcp_tools_from_config,
    load_mcp_tools_from_stdio_params
)

__all__ = [
    # Client classes and functions
    "BaseMCPClient",
    "StdioMCPClient", 
    "SSEMCPClient",
    "create_mcp_client",
    
    # Exceptions
    "MCPClientError",
    "MCPConnectionError", 
    "MCPToolExecutionError",
    
    # Tool adapter
    "MCPToolAdapter",
    "sanitize_function_name",
    "create_smolagents_tools_from_mcp_client",
    
    # Tool collection
    "CustomMCPToolCollection",
    "load_mcp_tools_from_config",
    "load_mcp_tools_from_stdio_params"
]
