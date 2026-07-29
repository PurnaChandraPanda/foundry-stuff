import asyncio
import httpx
import os

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from agent_framework import MCPStreamableHTTPTool
from agent_framework_foundry import FoundryChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv("../../src/agent-framework-agent-with-foundry-toolbox-responses/.env")

# ── Configuration ─────────────────────────────────────────────────────────────

endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
model_deployment = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
toolbox_name = "toolbox_ado"  # matches the toolbox name in Foundry
toolbox_url = os.environ["TOOLBOX_ENDPOINT"]

# ── Reusable functions (can be pulled into a hosted agent main.py) ────────────

# Toolbox MCP auth 
class _ToolboxAuth(httpx.Auth):
    """Injects a fresh bearer token on every request."""
    def __init__(self, token_provider):
        self._get_token = token_provider
    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


# [START msft_agentframework_toolbox]
_agent = None
_toolbox = None

async def create_agent_with_toolbox():
    """Create an Agent Framework agent wired to a Foundry toolbox via MCP."""
    global _agent, _toolbox

    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        credential, "https://ai.azure.com/.default"
    )

    http_client = httpx.AsyncClient(
        auth=_ToolboxAuth(token_provider),
        headers={"Foundry-Features": "Toolboxes=V1Preview"},
        timeout=120.0,
    )

    _toolbox = MCPStreamableHTTPTool(
        name=toolbox_name,
        url=toolbox_url,
        http_client=http_client,
        load_prompts=False,
    )

    chat_client = FoundryChatClient(
        project_endpoint=endpoint,
        model=model_deployment,
        credential=credential,
    )

    _agent = chat_client.as_agent(
        name="toolbox-agent",
        instructions="You are a helpful assistant with access to Azure AI Foundry toolbox tools.",
        tools=[_toolbox],
    )


async def call_agent_with_toolbox(user_input: str):
    """Send a message to the toolbox agent and print the response."""
    response = await _agent.run(messages=user_input, stream=False)
    print(response.text)


async def close_agent():
    """Close the toolbox MCP connection cleanly."""
    if _toolbox:
        await _toolbox.close()
# [END msft_agentframework_toolbox]


# ── Script entry point ────────────────────────────────────────────────────
async def main():
    await create_agent_with_toolbox()
    try:
        # message = "What tools are available?"
        message = 'List recent 3 commits in the project name: wfm-proxy, repo name: wfm-proxy, branch name: master'
        await call_agent_with_toolbox(message)
    finally:
        await close_agent()

asyncio.run(main())
