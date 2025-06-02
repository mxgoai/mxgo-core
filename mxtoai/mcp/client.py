import asyncio
import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Union

import mcp.types as mcp_types
from mcp import ClientSession, StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from smolagents import Tool

logger = logging.getLogger(__name__)


class MCPClientError(Exception):
    """Base exception for MCP client errors."""
    pass


class MCPConnectionError(MCPClientError):
    """Raised when MCP connection fails."""
    pass


class MCPToolExecutionError(MCPClientError):
    """Raised when MCP tool execution fails."""
    pass


class BaseMCPClient(ABC):
    """Base class for MCP clients."""
    
    def __init__(self, server_name: str):
        self.server_name = server_name
        self.session: Optional[ClientSession] = None
        self.is_connected = False
        self._tools: List[mcp_types.Tool] = []
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"mcp-{server_name}")
        
    @abstractmethod
    async def _create_session(self) -> ClientSession:
        """Create and return a new MCP session."""
        pass
    
    def connect(self) -> bool:
        """Connect to the MCP server synchronously."""
        try:
            future = self._executor.submit(self._run_async_connect)
            return future.result(timeout=30.0)  # 30 second timeout
        except Exception as e:
            logger.error(f"Failed to connect to MCP server {self.server_name}: {e}")
            return False
    
    def _run_async_connect(self) -> bool:
        """Run async connect in a new event loop."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._async_connect())
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Error in async connect wrapper: {e}")
            return False
    
    async def _async_connect(self) -> bool:
        """Async implementation of connect."""
        try:
            self.session = await self._create_session()
            
            # Initialize the session
            init_result = await self.session.initialize()
            logger.info(f"MCP server {self.server_name} initialized: {init_result}")
            
            # List available tools
            tools_result = await self.session.list_tools()
            self._tools = tools_result.tools
            logger.info(f"Found {len(self._tools)} tools from MCP server {self.server_name}")
            
            self.is_connected = True
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to MCP server {self.server_name}: {e}")
            self.is_connected = False
            return False
    
    def list_tools(self) -> List[mcp_types.Tool]:
        """List available tools from the MCP server."""
        if not self.is_connected:
            logger.warning(f"MCP server {self.server_name} is not connected")
            return []
        return self._tools.copy()
    
    def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool synchronously and return the result."""
        if not self.is_connected:
            raise MCPConnectionError(f"MCP server {self.server_name} is not connected")
        
        try:
            future = self._executor.submit(self._run_async_call_tool, tool_name, arguments)
            return future.result(timeout=60.0)  # 60 second timeout for tool execution
        except Exception as e:
            logger.error(f"Error calling tool {tool_name} on server {self.server_name}: {e}")
            raise MCPToolExecutionError(f"Tool execution failed: {e}") from e
    
    def _run_async_call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Run async tool call in a new event loop."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(self._async_call_tool(tool_name, arguments))
            finally:
                loop.close()
        except Exception as e:
            logger.error(f"Error in async tool call wrapper: {e}")
            raise
    
    async def _async_call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Async implementation of tool calling."""
        if not self.session:
            raise MCPConnectionError("No active session")
        
        try:
            result = await self.session.call_tool(tool_name, arguments)
            
            if not result.content:
                return ""
            
            # Extract text content from the result
            text_parts = []
            for content in result.content:
                if isinstance(content, mcp_types.TextContent):
                    text_parts.append(content.text)
                else:
                    # Handle other content types if needed
                    text_parts.append(str(content))
            
            return "\n".join(text_parts)
            
        except Exception as e:
            logger.error(f"Error in async tool call {tool_name}: {e}")
            raise
    
    def disconnect(self):
        """Disconnect from the MCP server."""
        if self.session:
            try:
                # Run cleanup in executor to handle async cleanup
                future = self._executor.submit(self._async_disconnect)
                future.result(timeout=10.0)
            except Exception as e:
                logger.error(f"Error during disconnect from {self.server_name}: {e}")
        
        self.is_connected = False
        self._tools = []
        
        # Shutdown the executor
        self._executor.shutdown(wait=True, timeout=5.0)
    
    async def _async_disconnect(self):
        """Async implementation of disconnect."""
        if self.session:
            try:
                # Close the session if it has a close method
                if hasattr(self.session, 'close'):
                    await self.session.close()
            except Exception as e:
                logger.error(f"Error closing session for {self.server_name}: {e}")
            finally:
                self.session = None


class StdioMCPClient(BaseMCPClient):
    """MCP client for stdio-based servers."""
    
    def __init__(self, server_name: str, server_params: StdioServerParameters):
        super().__init__(server_name)
        self.server_params = server_params
    
    async def _create_session(self) -> ClientSession:
        """Create a stdio-based MCP session."""
        try:
            read, write = await stdio_client(self.server_params)
            session = ClientSession(read, write)
            return session
        except Exception as e:
            logger.error(f"Failed to create stdio session for {self.server_name}: {e}")
            raise MCPConnectionError(f"Failed to create stdio session: {e}") from e


class SSEMCPClient(BaseMCPClient):
    """MCP client for SSE-based servers."""
    
    def __init__(self, server_name: str, url: str, **kwargs):
        super().__init__(server_name)
        self.url = url
        self.sse_kwargs = kwargs
    
    async def _create_session(self) -> ClientSession:
        """Create an SSE-based MCP session."""
        try:
            read, write = await sse_client(self.url, **self.sse_kwargs)
            session = ClientSession(read, write)
            return session
        except Exception as e:
            logger.error(f"Failed to create SSE session for {self.server_name}: {e}")
            raise MCPConnectionError(f"Failed to create SSE session: {e}") from e


@contextmanager
def create_mcp_client(server_name: str, server_config: Dict[str, Any]):
    """Factory function to create appropriate MCP client based on configuration."""
    client = None
    
    try:
        server_type = server_config.get("type")
        
        if server_type == "stdio":
            # Create StdioServerParameters
            command = server_config.get("command")
            args = server_config.get("args", [])
            env = server_config.get("env", {})
            
            if not command:
                raise ValueError(f"Stdio server {server_name} missing 'command'")
            
            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=env
            )
            client = StdioMCPClient(server_name, server_params)
            
        elif server_type == "sse":
            url = server_config.get("url")
            if not url:
                raise ValueError(f"SSE server {server_name} missing 'url'")
            
            extra_params = server_config.get("extra_params", {})
            client = SSEMCPClient(server_name, url, **extra_params)
            
        else:
            raise ValueError(f"Unknown server type: {server_type}")
        
        # Connect to the server
        if not client.connect():
            raise MCPConnectionError(f"Failed to connect to MCP server {server_name}")
        
        logger.info(f"Successfully connected to MCP server {server_name}")
        yield client
        
    except Exception as e:
        logger.error(f"Error with MCP server {server_name}: {e}")
        raise
    finally:
        if client:
            try:
                client.disconnect()
                logger.info(f"Disconnected from MCP server {server_name}")
            except Exception as e:
                logger.error(f"Error disconnecting from {server_name}: {e}")
