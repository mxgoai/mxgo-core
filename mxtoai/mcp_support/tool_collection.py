import os
import logging
from contextlib import contextmanager
from typing import Dict, List, Any, Union

from smolagents import Tool
from mcp import StdioServerParameters

from .client import create_mcp_client, MCPConnectionError
from .tool_adapter import create_smolagents_tools_from_mcp_client

logger = logging.getLogger(__name__)


class CustomMCPToolCollection:
    """
    Custom MCP tool collection that replaces smolagents ToolCollection.from_mcp
    """
    
    def __init__(self, tools: List[Tool]):
        self.tools = tools
    
    def __len__(self) -> int:
        return len(self.tools)
    
    def __iter__(self):
        return iter(self.tools)
    
    def __getitem__(self, index):
        return self.tools[index]
    
    @classmethod
    @contextmanager
    def from_mcp_config(cls, mcp_servers_config: Dict[str, Dict[str, Any]]):
        """
        Create a tool collection from MCP server configurations.
        
        Args:
            mcp_servers_config: Dictionary of server configurations from mcp.toml
            
        Yields:
            CustomMCPToolCollection: Collection of adapted MCP tools
        """
        active_clients = []
        all_tools = []
        
        try:
            for server_name, server_config in mcp_servers_config.items():
                if not server_config.get("enabled", True):
                    logger.debug(f"MCP server '{server_name}' is disabled, skipping")
                    continue
                
                try:
                    logger.info(f"Connecting to MCP server '{server_name}'")
                    
                    # Create and connect to MCP client
                    client_ctx = create_mcp_client(server_name, server_config)
                    mcp_client = client_ctx.__enter__()
                    active_clients.append((mcp_client, client_ctx))
                        
                    # Adapt tools from this client
                    adapted_tools = create_smolagents_tools_from_mcp_client(mcp_client)
                    all_tools.extend(adapted_tools)
                    
                    logger.info(f"Successfully loaded {len(adapted_tools)} tools from '{server_name}'")
                        
                except Exception as e:
                    logger.error(f"Failed to connect to MCP server '{server_name}': {e}")
                    continue
            
            logger.info(f"Total MCP tools loaded: {len(all_tools)} from {len(active_clients)} servers")
            
            # Yield the tool collection
            yield cls(all_tools)
            
        except Exception as e:
            logger.error(f"Error in MCP tool collection context manager: {e}")
            raise
        finally:
            # Cleanup all active clients
            for mcp_client, client_ctx in active_clients:
                try:
                    client_ctx.__exit__(None, None, None)
                    logger.debug(f"Cleaned up MCP client: {mcp_client.server_name}")
                except Exception as e:
                    logger.error(f"Error cleaning up MCP client {mcp_client.server_name}: {e}")
            logger.debug("MCP tool collection context manager cleanup completed")
    
    @classmethod 
    @contextmanager
    def from_single_server(cls, server_name: str, server_config: Dict[str, Any]):
        """
        Create a tool collection from a single MCP server.
        
        Args:
            server_name: Name of the MCP server
            server_config: Server configuration dictionary
            
        Yields:
            CustomMCPToolCollection: Collection of adapted MCP tools
        """
        try:
            logger.info(f"Connecting to single MCP server '{server_name}'")
            
            with create_mcp_client(server_name, server_config) as mcp_client:
                adapted_tools = create_smolagents_tools_from_mcp_client(mcp_client)
                logger.info(f"Successfully loaded {len(adapted_tools)} tools from '{server_name}'")
                
                yield cls(adapted_tools)
                
        except Exception as e:
            logger.error(f"Failed to connect to MCP server '{server_name}': {e}")
            # Yield empty collection on failure
            yield cls([])


@contextmanager
def load_mcp_tools_from_config(mcp_servers_config: Dict[str, Dict[str, Any]]) -> List[Tool]:
    """
    Convenience function to load MCP tools from configuration.
    
    Args:
        mcp_servers_config: Dictionary of server configurations
        
    Yields:
        List[Tool]: List of smolagents Tool instances
    """
    with CustomMCPToolCollection.from_mcp_config(mcp_servers_config) as tool_collection:
        yield tool_collection.tools


@contextmanager 
def load_mcp_tools_from_stdio_params(server_params: Union[StdioServerParameters, Dict[str, Any]], server_name: str = "mcp_server") -> List[Tool]:
    """
    Load MCP tools from StdioServerParameters or SSE config dict.
    This provides compatibility with the original smolagents interface.
    
    Args:
        server_params: StdioServerParameters or SSE config dict
        server_name: Name for the server (for logging)
        
    Yields:
        List[Tool]: List of smolagents Tool instances
    """
    # Convert to our config format
    if isinstance(server_params, StdioServerParameters):
        server_config = {
            "type": "stdio",
            "command": server_params.command,
            "args": server_params.args,
            "env": server_params.env,
            "enabled": True
        }
    elif isinstance(server_params, dict):
        # Assume it's SSE config
        server_config = {
            "type": "sse",
            "enabled": True,
            **server_params
        }
    else:
        raise ValueError(f"Unsupported server_params type: {type(server_params)}")
    
    with CustomMCPToolCollection.from_single_server(server_name, server_config) as tool_collection:
        yield tool_collection.tools
