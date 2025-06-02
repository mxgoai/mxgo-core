import os
import logging
from dotenv import load_dotenv

from mcp import StdioServerParameters
from smolagents import CodeAgent, AzureOpenAIServerModel # Changed import from LiteLLMModel
from mcpadapt.core import MCPAdapt
from mcpadapt.smolagents_adapter import SmolAgentsAdapter

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_github_agent_example():
    """
    Runs a SmolAgent ToolCallingAgent with GitHub MCP tools via MCPAdapt
    to list repositories and issue counts for a user, using Azure OpenAI.
    """
    # Load environment variables from .env file
    load_dotenv()

    github_pat = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    if not github_pat:
        logger.error("GITHUB_PERSONAL_ACCESS_TOKEN not found in environment variables.")
        logger.error("Please set it in your .env file or environment.")
        return

    # Azure OpenAI environment variables
    azure_openai_model = os.getenv("AZURE_OPENAI_MODEL", "o3-mini-deep-research")
    azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "https://gauta-m45ryzo6-eastus2.cognitiveservices.azure.com/")
    azure_openai_api_key = os.getenv("AZURE_OPENAI_API_KEY", "3MmGJJxhTpDBUYykqxUZoe4UAVMxsBnY6R9rRdpvnlOLhb3vngk6JQQJ99ALACHYHv6XJ3w3AAAAACOG67Gz")
    openai_api_version = os.getenv("OPENAI_API_VERSION", "2024-12-01-preview")

    if not all([azure_openai_model, azure_openai_endpoint, azure_openai_api_key, openai_api_version]):
        logger.error("One or more Azure OpenAI environment variables are missing.")
        logger.error("Please ensure AZURE_OPENAI_MODEL, AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY, and OPENAI_API_VERSION are set.")
        return

    logger.info(f"Using Azure OpenAI Model: {azure_openai_model} at endpoint: {azure_openai_endpoint}")

    # Configure MCP StdioServerParameters for the GitHub Docker runner
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

    query = "List down all the github repositories of satwikkansal along with number of issues in top 3 of them"
    logger.info(f"Agent Query: {query}")

    try:
        # Use MCPAdapt to make MCP tools available
        with MCPAdapt(
            mcp_server_params,
            SmolAgentsAdapter(),
        ) as mcp_tools:
            if not mcp_tools:
                logger.error("No tools loaded from MCP. Check MCP server and configuration.")
                return

            logger.info(f"Successfully loaded {len(mcp_tools)} tools from GitHub MCP server.")
            
            # Initialize the AzureOpenAIServerModel
            model = AzureOpenAIServerModel(
                model_id=azure_openai_model,
                azure_endpoint=azure_openai_endpoint,
                api_key=azure_openai_api_key,
                api_version=openai_api_version    
            )
            logger.info("AzureOpenAIServerModel initialized.")

            # Initialize ToolCallingAgent
            agent = CodeAgent(
                tools=mcp_tools, # Tools from MCPAdapt
                model=model,
                max_steps=10, # Adjust as needed
                verbosity_level=1 # 0 for quiet, 1 for tool calls, 2 for thoughts
            )
            logger.info("ToolCallingAgent initialized.")

            # Run the agent
            logger.info("Running agent...")
            result = agent.run(query)

            logger.info("Agent execution finished.")
            print("\n--- Agent Result ---")
            print(result)
            print("--- End of Agent Result ---")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)

if __name__ == "__main__":
    run_github_agent_example() 