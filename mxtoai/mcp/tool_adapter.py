import json
import keyword
import logging
import re
from typing import Any, Dict, List, Optional

import jsonref
import mcp.types as mcp_types
from smolagents import Tool

from .client import BaseMCPClient, MCPToolExecutionError

logger = logging.getLogger(__name__)


def sanitize_function_name(name: str) -> str:
    """
    Sanitize function names to be valid Python identifiers.
    Based on MCPAdapt's implementation but with improvements.
    """
    # Replace dashes and other non-alphanumeric chars with underscores
    name = re.sub(r"[^\w]", "_", name)
    
    # Remove consecutive underscores
    name = re.sub(r"_{2,}", "_", name)
    
    # Ensure it doesn't start with a number
    if name and name[0].isdigit():
        name = f"tool_{name}"
    
    # Check if it's a Python keyword
    if keyword.iskeyword(name):
        name = f"{name}_tool"
    
    # Ensure it's not empty
    if not name:
        name = "unnamed_tool"
    
    return name


class MCPToolAdapter:
    """Adapter to convert MCP tools to smolagents Tools."""
    
    def __init__(self):
        self.adapted_tools: Dict[str, Tool] = {}
    
    def adapt_mcp_tool(self, mcp_tool: mcp_types.Tool, mcp_client: BaseMCPClient) -> Tool:
        """Convert an MCP tool to a smolagents Tool."""
        
        sanitized_name = sanitize_function_name(mcp_tool.name)
        
        class MCPAdaptedTool(Tool):
            def __init__(self, original_name: str, mcp_client: BaseMCPClient):
                self.original_name = original_name
                self.mcp_client = mcp_client
                self.name = sanitized_name
                self.description = mcp_tool.description or f"MCP tool: {original_name}"
                self.inputs = self._convert_input_schema(mcp_tool.inputSchema)
                self.output_type = "string"  # MCP tools return text content
                self.is_initialized = True
                self.skip_forward_signature_validation = True
            
            def _convert_input_schema(self, input_schema: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
                """Convert MCP input schema to smolagents format."""
                if not input_schema:
                    return {}
                
                # Resolve JSON references
                try:
                    resolved_schema = jsonref.replace_refs(input_schema)
                except Exception as e:
                    logger.warning(f"Failed to resolve JSON refs for {mcp_tool.name}: {e}")
                    resolved_schema = input_schema
                
                properties = resolved_schema.get("properties", {})
                converted_inputs = {}
                
                for param_name, param_info in properties.items():
                    param_type = param_info.get("type", "string")
                    param_description = param_info.get("description", "Parameter for MCP tool")
                    
                    # Map JSON schema types to smolagents types
                    smolagents_type = self._map_json_type_to_smolagents(param_type)
                    
                    converted_inputs[param_name] = {
                        "type": smolagents_type,
                        "description": param_description
                    }
                    
                    # Handle nullable parameters
                    if param_info.get("nullable", False):
                        converted_inputs[param_name]["nullable"] = True
                
                return converted_inputs
            
            def _map_json_type_to_smolagents(self, json_type: str) -> str:
                """Map JSON schema types to smolagents types."""
                type_mapping = {
                    "string": "string",
                    "integer": "integer", 
                    "number": "number",
                    "boolean": "boolean",
                    "array": "array",
                    "object": "object"
                }
                return type_mapping.get(json_type, "string")
            
            def forward(self, *args, **kwargs) -> str:
                """Execute the MCP tool."""
                try:
                    # Handle arguments - convert positional args to kwargs if needed
                    tool_args = {}
                    
                    if len(args) == 1 and isinstance(args[0], dict) and not kwargs:
                        # Single dict argument
                        tool_args = args[0]
                    elif args and not kwargs:
                        # Multiple positional arguments - map to input parameters
                        input_keys = list(self.inputs.keys())
                        for i, arg in enumerate(args):
                            if i < len(input_keys):
                                tool_args[input_keys[i]] = arg
                    else:
                        # Use keyword arguments
                        tool_args = kwargs
                    
                    # Call the MCP tool through the client
                    result = self.mcp_client.call_tool(self.original_name, tool_args)
                    return result
                    
                except Exception as e:
                    error_msg = f"Error executing MCP tool {self.original_name}: {e}"
                    logger.error(error_msg)
                    raise MCPToolExecutionError(error_msg) from e
        
        # Create and return the adapted tool
        adapted_tool = MCPAdaptedTool(mcp_tool.name, mcp_client)
        self.adapted_tools[sanitized_name] = adapted_tool
        
        logger.debug(f"Adapted MCP tool '{mcp_tool.name}' -> '{sanitized_name}'")
        return adapted_tool
    
    def adapt_all_tools(self, mcp_client: BaseMCPClient) -> List[Tool]:
        """Adapt all tools from an MCP client."""
        adapted_tools = []
        
        try:
            mcp_tools = mcp_client.list_tools()
            logger.info(f"Adapting {len(mcp_tools)} tools from MCP server {mcp_client.server_name}")
            
            for mcp_tool in mcp_tools:
                try:
                    adapted_tool = self.adapt_mcp_tool(mcp_tool, mcp_client)
                    adapted_tools.append(adapted_tool)
                    logger.debug(f"Successfully adapted tool: {mcp_tool.name}")
                except Exception as e:
                    logger.error(f"Failed to adapt tool {mcp_tool.name}: {e}")
                    continue
            
            logger.info(f"Successfully adapted {len(adapted_tools)} tools from {mcp_client.server_name}")
            return adapted_tools
            
        except Exception as e:
            logger.error(f"Error adapting tools from {mcp_client.server_name}: {e}")
            return []
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get information about an adapted tool."""
        if tool_name in self.adapted_tools:
            tool = self.adapted_tools[tool_name]
            return {
                "name": tool.name,
                "description": tool.description,
                "inputs": tool.inputs,
                "output_type": tool.output_type,
                "original_name": getattr(tool, "original_name", tool_name)
            }
        return None
    
    def list_adapted_tools(self) -> List[str]:
        """List all adapted tool names."""
        return list(self.adapted_tools.keys())


def create_smolagents_tools_from_mcp_client(mcp_client: BaseMCPClient) -> List[Tool]:
    """
    Convenience function to create smolagents tools from an MCP client.
    
    Args:
        mcp_client: Connected MCP client
        
    Returns:
        List of smolagents Tool instances
    """
    adapter = MCPToolAdapter()
    return adapter.adapt_all_tools(mcp_client)
