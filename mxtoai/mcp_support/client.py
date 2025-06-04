import asyncio
import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

# Import from the official MCP library using specific paths to avoid local package conflict
import mcp.types as mcp_types
from mcp import StdioServerParameters
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client

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
        self._event_loop = None  # Store the event loop used for connection
        
    @abstractmethod
    async def _create_session(self) -> ClientSession:
        """Create and return a new MCP session."""
        pass
    
    def connect(self) -> bool:
        """Connect to the MCP server synchronously."""
        logger.info(f"Attempting to connect to MCP server {self.server_name}...")
        try:
            future = self._executor.submit(self._run_async_connect)
            result = future.result(timeout=30.0)  # 30 second timeout
            if result:
                logger.info(f"Successfully connected to MCP server {self.server_name}")
            else:
                logger.error(f"Failed to connect to MCP server {self.server_name}")
            return result
        except Exception as e:
            logger.error(f"Failed to connect to MCP server {self.server_name}: {e}", exc_info=True)
            return False
    
    def _run_async_connect(self) -> bool:
        """Run async connect in a new event loop and store it for reuse."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._event_loop = loop  # Store the loop for reuse
            try:
                return loop.run_until_complete(self._async_connect())
            except Exception as e:
                logger.error(f"Error in _async_connect: {e}", exc_info=True)
                return False
            # Note: We don't close the loop here since we need to reuse it for tool calls
        except Exception as e:
            logger.error(f"Error in async connect wrapper for {self.server_name}: {e}", exc_info=True)
            return False
    
    async def _async_connect(self) -> bool:
        """Async implementation of connect."""
        try:
            logger.info(f"Creating session for MCP server {self.server_name}...")
            self.session = await self._create_session()
            logger.info(f"Session created successfully for {self.server_name}")
            
            # Initialize the session with timeout
            logger.info(f"Initializing MCP server {self.server_name}...")
            init_result = await asyncio.wait_for(
                self.session.initialize(), 
                timeout=30.0  # 30 second timeout for initialization
            )
            logger.info(f"MCP server {self.server_name} initialized: {init_result}")
            
            # List available tools
            logger.info(f"Listing tools from MCP server {self.server_name}...")
            tools_result = await asyncio.wait_for(
                self.session.list_tools(),
                timeout=10.0  # 10 second timeout for listing tools
            )
            self._tools = tools_result.tools
            logger.info(f"Found {len(self._tools)} tools from MCP server {self.server_name}")
            
            self.is_connected = True
            return True
            
        except asyncio.TimeoutError as e:
            logger.error(f"Timeout connecting to MCP server {self.server_name}: {e}")
            self.is_connected = False
            return False
        except Exception as e:
            logger.error(f"Error connecting to MCP server {self.server_name}: {e}", exc_info=True)
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
        """Run async tool call in the stored event loop."""
        if not self._event_loop:
            raise MCPConnectionError("No event loop available - connection not established")
        
        try:
            # Set the stored event loop as current and run the async call
            asyncio.set_event_loop(self._event_loop)
            return self._event_loop.run_until_complete(self._async_call_tool(tool_name, arguments))
        except Exception as e:
            logger.error(f"Error in async tool call wrapper: {e}", exc_info=True)
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
        logger.info(f"Disconnecting from MCP server {self.server_name}...")
        if self.session and self._event_loop:
            try:
                # Run cleanup in the stored event loop
                asyncio.set_event_loop(self._event_loop)
                self._event_loop.run_until_complete(self._async_disconnect())
            except Exception as e:
                logger.error(f"Error during disconnect from {self.server_name}: {e}", exc_info=True)
        
        # Clean up event loop
        if self._event_loop:
            try:
                self._event_loop.close()
            except Exception as e:
                logger.error(f"Error closing event loop for {self.server_name}: {e}")
            finally:
                self._event_loop = None
        
        self.is_connected = False
        self._tools = []
        
        # Shutdown the executor
        self._executor.shutdown(wait=True)
        logger.info(f"Disconnected from MCP server {self.server_name}")

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
        self.stdio_context = None
        self.session_context = None
        self.read_stream = None
        self.write_stream = None
    
    async def _create_session(self) -> ClientSession:
        """Create a stdio-based MCP session using proper async context managers."""
        try:
            logger.info(f"Creating stdio client for {self.server_name} with command: {self.server_params.command} {' '.join(self.server_params.args)}")
            
            # Create and enter the stdio context manager
            self.stdio_context = stdio_client(self.server_params)
            logger.info(f"Stdio context manager created for {self.server_name}")
            
            logger.info(f"Entering stdio context for {self.server_name}...")
            self.read_stream, self.write_stream = await self.stdio_context.__aenter__()
            logger.info(f"Stdio streams established for {self.server_name}")
            
            # Create and enter the session context manager
            self.session_context = ClientSession(self.read_stream, self.write_stream)
            session = await self.session_context.__aenter__()
            logger.info(f"ClientSession context entered for {self.server_name}")
            return session
        except Exception as e:
            logger.error(f"Failed to create stdio session for {self.server_name}: {e}", exc_info=True)
            # Clean up on failure
            await self._cleanup_contexts(e)
            raise MCPConnectionError(f"Failed to create stdio session: {e}") from e
    
    async def _cleanup_contexts(self, exception=None):
        """Clean up both session and stdio contexts."""
        # Clean up session context first
        if self.session_context:
            try:
                if exception:
                    await self.session_context.__aexit__(type(exception), exception, exception.__traceback__)
                else:
                    await self.session_context.__aexit__(None, None, None)
            except Exception as cleanup_error:
                logger.error(f"Error closing session context for {self.server_name}: {cleanup_error}")
            finally:
                self.session_context = None
        
        # Then clean up stdio context
        if self.stdio_context:
            try:
                if exception:
                    await self.stdio_context.__aexit__(type(exception), exception, exception.__traceback__)
                else:
                    await self.stdio_context.__aexit__(None, None, None)
            except Exception as cleanup_error:
                logger.error(f"Error closing stdio context for {self.server_name}: {cleanup_error}")
            finally:
                self.stdio_context = None
                self.read_stream = None
                self.write_stream = None
    
    async def _async_disconnect(self):
        """Async implementation of disconnect with proper context cleanup."""
        # Note: We don't need to call session.close() since we're using context managers
        self.session = None
        await self._cleanup_contexts()


class SSEMCPClient(BaseMCPClient):
    """MCP client for SSE-based servers."""
    
    def __init__(self, server_name: str, url: str, **kwargs):
        super().__init__(server_name)
        self.url = url
        self.sse_kwargs = kwargs
        self.sse_context = None
        self.read_stream = None
        self.write_stream = None
    
    async def _create_session(self) -> ClientSession:
        """Create an SSE-based MCP session."""
        try:
            # Create the SSE context manager
            self.sse_context = sse_client(self.url, **self.sse_kwargs)
            # Enter the context manager
            self.read_stream, self.write_stream = await self.sse_context.__aenter__()
            # Create session with the streams
            session = ClientSession(self.read_stream, self.write_stream)
            return session
        except Exception as e:
            logger.error(f"Failed to create SSE session for {self.server_name}: {e}")
            # Clean up on failure
            if self.sse_context:
                try:
                    await self.sse_context.__aexit__(type(e), e, e.__traceback__)
                except:
                    pass  # Ignore cleanup errors
                self.sse_context = None
            raise MCPConnectionError(f"Failed to create SSE session: {e}") from e
    
    async def _async_disconnect(self):
        """Async implementation of disconnect with proper SSE cleanup."""
        # Close the session first
        if self.session:
            try:
                # Close the session if it has a close method
                if hasattr(self.session, 'close'):
                    await self.session.close()
            except Exception as e:
                logger.error(f"Error closing session for {self.server_name}: {e}")
            finally:
                self.session = None
        
        # Clean up SSE context
        if self.sse_context:
            try:
                await self.sse_context.__aexit__(None, None, None)
            except Exception as e:
                logger.error(f"Error closing SSE context for {self.server_name}: {e}")
            finally:
                self.sse_context = None
                self.read_stream = None
                self.write_stream = None


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