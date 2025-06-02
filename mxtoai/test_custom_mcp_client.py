"""
Test script to demonstrate the custom MCP client implementation.
This replaces the dependency on MCPAdapt library.
"""

import os
import logging
from dotenv import load_dotenv

from smolagents import CodeAgent, AzureOpenAIServerModel
from mxtoai.mcp import load_mcp_tools_from_stdio_params
from mcp import StdioServerParameters

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_custom_mcp_github_client():
    """
    Test our custom MCP client with GitHub MCP tools.
    This demonstrates the replacement of MCPAdapt with our custom implementation.
    """
    # Load environment variables
    load_dotenv()

    github_pat = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not github_pat:
        logger.error("GITHUB_PERSONAL_ACCESS_TOKEN not found in environment variables.")
        logger.error("Please set it in your .env file or environment.")
        return

    # Azure OpenAI environment variables
    azure_openai_model = os.getenv("AZURE_OPENAI_MODEL", "o3-mini-deep-research")
    azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
    openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-12-01-preview")

    if not all([azure_openai_model, azure_openai_endpoint, azure_openai_api_key]):
        logger.error("One or more Azure OpenAI environment variables are missing.")
        logger.error("Please ensure AZURE_OPENAI_MODEL, AZURE_OPENAI_ENDPOINT, and AZURE_OPENAI_API_KEY are set.")
        return

    logger.info(f"Using Azure OpenAI Model: {azure_openai_model} at endpoint: {azure_openai_endpoint}")

    # Configure MCP StdioServerParameters for the GitHub server
    mcp_server_params = StdioServerParameters(
        command="docker",
        args=[
            "run",
            "-i",  # Interactive mode to allow stdio communication
            "--rm", # Remove container after exit
            "-e", f"GITHUB_PERSONAL_ACCESS_TOKEN={github_pat}", # Pass PAT to the container
            "ghcr.io/github/github-mcp-server"
        ],
        env=os.environ.copy() # Pass current environment to the Docker command itself
    )
    logger.info(f"Configured MCP server with command: docker and image: ghcr.io/github/github-mcp-server")

    query = "List the repositories of satwikkansal and show the number of issues for the top 3 repositories"
    logger.info(f"Agent Query: {query}")

    try:
        # Use our custom MCP implementation
        logger.info("Testing custom MCP client implementation...")
        
        with load_mcp_tools_from_stdio_params(mcp_server_params, "github_server") as mcp_tools:
            if not mcp_tools:
                logger.error("No tools loaded from MCP. Check MCP server and configuration.")
                return

            logger.info(f"Successfully loaded {len(mcp_tools)} tools from GitHub MCP server using custom client.")
            
            # Log the available tools
            for tool in mcp_tools:
                logger.info(f"Available tool: {tool.name} - {tool.description}")
            
            # Initialize the AzureOpenAIServerModel
            model = AzureOpenAIServerModel(
                model_id=azure_openai_model,
                azure_endpoint=azure_openai_endpoint,
                api_key=azure_openai_api_key,
                api_version=openai_api_version    
            )
            logger.info("AzureOpenAIServerModel initialized.")

            # Initialize CodeAgent with custom MCP tools
            agent = CodeAgent(
                tools=mcp_tools,
                model=model,
                max_steps=10,
                verbosity_level=1
            )
            logger.info("CodeAgent initialized with custom MCP tools.")

            # Run the agent
            logger.info("Running agent with custom MCP client...")
            result = agent.run(query)

            logger.info("Agent execution finished.")
            print("\n--- Custom MCP Client Result ---")
            print(result)
            print("--- End of Custom MCP Client Result ---")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)


def test_custom_mcp_config_loading():
    """
    Test loading MCP tools from configuration file.
    """
    logger.info("Testing MCP configuration loading...")
    
    # This would use the mcp.toml file if it exists
    from mxtoai.agents.email_agent import EmailAgent
    
    try:
        agent = EmailAgent(verbose=True)
        mcp_config = agent._get_mcp_servers_config()
        
        if mcp_config:
            logger.info(f"Found {len(mcp_config)} MCP servers in configuration:")
            for server_name, config in mcp_config.items():
                logger.info(f"- {server_name}: {config.get('type', 'unknown')} server")
        else:
            logger.info("No MCP servers found in configuration")
            
    except Exception as e:
        logger.error(f"Error testing MCP config loading: {e}", exc_info=True)


if __name__ == "__main__":
    print("Testing Custom MCP Client Implementation")
    print("=" * 50)
    
    # Test 1: Direct MCP client usage
    print("\n1. Testing direct MCP client with GitHub server...")
    test_custom_mcp_github_client()
    
    print("\n" + "=" * 50)
    
    # Test 2: Configuration loading
    print("\n2. Testing MCP configuration loading...")
    test_custom_mcp_config_loading()
    
    print("\nCustom MCP client tests completed!")
