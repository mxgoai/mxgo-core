# MCP Migration Guide: From MCPAdapt to Custom Implementation

## Overview

This document describes the migration from the `MCPAdapt` library dependency to a custom Model Context Protocol (MCP) client implementation for the mxtoai project.

## Background

The original implementation used:
- `smolagents.ToolCollection.from_mcp()` which relied on the `MCPAdapt` library
- External dependency on `mcpadapt.smolagents_adapter.SmolAgentsAdapter`

**Issues with the original approach:**
- MCPAdapt library wasn't working reliably
- Limited control over MCP client behavior
- Difficult to debug and customize
- Dependency on external library for core functionality

## New Custom Implementation

### Architecture

```
mxtoai/mcp/
├── __init__.py              # Module exports
├── client.py                # Core MCP client implementation
├── tool_adapter.py          # MCP-to-smolagents tool conversion
└── tool_collection.py       # Tool collection with context managers
```

### Key Components

#### 1. MCP Client (`client.py`)
- **BaseMCPClient**: Abstract base class for MCP clients
- **StdioMCPClient**: Handles stdio-based MCP servers (e.g., Docker containers)
- **SSEMCPClient**: Handles Server-Sent Events MCP servers
- **Synchronous Interface**: Wraps async MCP operations for smolagents compatibility

```python
# Factory function for creating MCP clients
with create_mcp_client(server_name, server_config) as client:
    tools = client.list_tools()
    result = client.call_tool("tool_name", {"arg": "value"})
```

#### 2. Tool Adapter (`tool_adapter.py`)
- **MCPToolAdapter**: Converts MCP tools to smolagents Tool instances
- **Function Name Sanitization**: Handles Python keyword conflicts and naming issues
- **Schema Conversion**: Maps MCP JSON schemas to smolagents input formats

```python
adapter = MCPToolAdapter()
smolagents_tools = adapter.adapt_all_tools(mcp_client)
```

#### 3. Tool Collection (`tool_collection.py`)
- **CustomMCPToolCollection**: Replacement for smolagents ToolCollection.from_mcp
- **Context Managers**: Proper resource management for MCP connections
- **Configuration Loading**: Direct integration with mcp.toml format

```python
# Load from configuration
with load_mcp_tools_from_config(mcp_servers_config) as tools:
    agent = ToolCallingAgent(tools=tools, ...)

# Load from parameters (backward compatibility)
with load_mcp_tools_from_stdio_params(server_params) as tools:
    agent = CodeAgent(tools=tools, ...)
```

### Features

#### ✅ Synchronous Operation
- Compatible with smolagents (no async support)
- Works with Dramatiq workers
- Proper event loop management

#### ✅ Dual Server Support
- **Stdio servers**: Docker containers, local processes
- **SSE servers**: HTTP-based MCP servers

#### ✅ Robust Error Handling
- Connection timeouts and retries
- Graceful fallback to base tools
- Detailed logging and debugging

#### ✅ Resource Management
- Automatic connection cleanup
- Context managers for safe resource handling
- Thread pool management for async operations

#### ✅ Configuration Integration
- Native mcp.toml support
- Environment variable merging
- Server enable/disable controls

## Migration Changes

### EmailAgent Updates

**Before (MCPAdapt):**
```python
from smolagents import ToolCollection

with ToolCollection.from_mcp(params, trust_remote_code=True) as tool_collection:
    all_tools.extend(tool_collection.tools)
```

**After (Custom Implementation):**
```python
from mxtoai.mcp import load_mcp_tools_from_config

mcp_servers_config = self._get_mcp_servers_config()
with load_mcp_tools_from_config(mcp_servers_config) as mcp_tools:
    all_tools.extend(mcp_tools)
```

### Configuration Format

The `mcp.toml` format remains the same, but now uses native parsing:

```toml
[mcp_servers.github_stdio]
type = "stdio"
command = "docker"
args = ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"]
env = { GITHUB_PERSONAL_ACCESS_TOKEN = "your_token" }
enabled = true

[mcp_servers.remote_sse_service]
type = "sse"
url = "http://127.0.0.1:8000/sse"
enabled = true
```

## Benefits of Custom Implementation

### 🚀 Performance
- Reduced dependency overhead
- Optimized for synchronous operation
- Better resource management

### 🔧 Control & Debugging
- Full control over MCP client behavior
- Detailed logging at every step
- Easy to extend and customize

### 🛡️ Reliability
- No external library dependency issues
- Robust error handling and recovery
- Proper connection lifecycle management

### 🔄 Maintainability
- Clean, documented codebase
- Modular architecture
- Easy to test and modify

## Testing

### Test Script
Run the migration test:
```bash
python mxtoai/test_custom_mcp_client.py
```

### Integration Testing
The custom implementation is fully integrated into:
- EmailAgent.process_email()
- MCP server configuration loading
- Tool adaptation and execution

## Security Considerations

The custom implementation maintains the same security model:
- **Trust Remote Code**: Still required for MCP tool execution
- **Environment Isolation**: Docker containers for stdio servers
- **Configuration Validation**: Server configs are validated before use

## Backward Compatibility

The migration maintains backward compatibility:
- Same mcp.toml configuration format
- Same smolagents Tool interface
- Same agent execution patterns

## Migration Checklist

- [x] Implement core MCP client classes
- [x] Create tool adaptation layer
- [x] Build tool collection with context managers
- [x] Update EmailAgent to use custom implementation
- [x] Remove MCPAdapt dependency usage
- [x] Create test and validation scripts
- [x] Document migration process
- [x] Maintain configuration compatibility

## Next Steps

1. **Remove MCPAdapt Dependency**: Update pyproject.toml to remove mcpadapt requirement
2. **Performance Testing**: Test with various MCP servers to ensure performance
3. **Documentation Updates**: Update README and API documentation
4. **Production Deployment**: Deploy and monitor in production environment

## Troubleshooting

### Common Issues

**Connection Timeouts**
```python
# Increase timeout in client.py if needed
future.result(timeout=60.0)  # Adjust as needed
```

**Tool Name Conflicts**
```python
# Function names are automatically sanitized
# Check logs for name mappings: "tool-name" -> "tool_name"
```

**Environment Variables**
```python
# Ensure MCP server env vars are properly merged
server_config["env"] = {**os.environ, **server_config["env"]}
```

This custom implementation provides a robust, maintainable, and performant replacement for the MCPAdapt library dependency.
