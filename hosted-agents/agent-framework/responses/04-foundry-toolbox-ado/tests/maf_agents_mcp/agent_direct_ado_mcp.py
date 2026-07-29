import asyncio
import httpx
import os

from azure.identity import DefaultAzureCredential, get_bearer_token_provider, AzureCliCredential
from agent_framework import MCPStreamableHTTPTool
from agent_framework_foundry import FoundryChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv("../../src/agent-framework-agent-with-foundry-toolbox-responses/.env")

# ── Configuration ─────────────────────────────────────────────────────────────

endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
model_deployment = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]

# ADO MCP server directly (bypass toolbox)
ado_org = "cssdevs"
ado_mcp_url = f"https://mcp.dev.azure.com/{ado_org}"

# ── Auth for ADO MCP (your user token directly) ──────────────────────────────

class _AdoMcpAuth(httpx.Auth):
    """Injects a fresh bearer token for the ADO MCP audience."""
    def __init__(self, token_provider):
        self._get_token = token_provider
    def auth_flow(self, request):
        request.headers["Authorization"] = f"Bearer {self._get_token()}"
        yield request


# ── Agent setup ───────────────────────────────────────────────────────────────
_agent = None
_ado_tool = None

async def create_agent():
    global _agent, _ado_tool

    credential = DefaultAzureCredential()
    # credential = AzureCliCredential()

    # Token for ADO MCP server (audience: https://mcp.dev.azure.com)
    ado_token_provider = get_bearer_token_provider(
        credential, "https://mcp.dev.azure.com"
    )

    http_client = httpx.AsyncClient(
        auth=_AdoMcpAuth(ado_token_provider),
        timeout=120.0,
    )

    _ado_tool = MCPStreamableHTTPTool(
        name="ado",
        url=ado_mcp_url,
        http_client=http_client,
        load_prompts=False,
    )

    chat_client = FoundryChatClient(
        project_endpoint=endpoint,
        model=model_deployment,
        credential=credential,
    )

    _agent = chat_client.as_agent(
        name="ado-agent",
        instructions="You are a helpful assistant with access to Azure DevOps tools.",
        tools=[_ado_tool],
    )


async def call_agent(user_input: str):
    response = await _agent.run(messages=user_input, stream=False)
    print(response.text)


async def close_agent():
    if _ado_tool:
        await _ado_tool.close()


# ── Entry point ───────────────────────────────────────────────────────────────
async def main():
    await create_agent()
    try:
        message = 'List recent 3 commits in the project name: wfm-proxy, repo name: wfm-proxy, branch name: master'
        await call_agent(message)
    finally:
        await close_agent()

asyncio.run(main())