import asyncio
import httpx
import os
import sys
from pathlib import Path

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from agent_framework import Agent, MCPSkillsSource, MCPStreamableHTTPTool, SkillsProvider
from agent_framework_foundry import FoundryChatClient
from dotenv import load_dotenv

# Load environment variables from .env file
SAMPLE_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(SAMPLE_ROOT / "src" / "agent-framework-agent-foundry-skills-responses" / ".env")

# ── Configuration ─────────────────────────────────────────────────────────────

endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
model_deployment = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
toolbox_name = os.environ["TOOLBOX_NAME"]
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
        load_tools=False,
        load_prompts=False,
    )
    await _toolbox.connect()
    if _toolbox.session is None:
        raise RuntimeError("Foundry toolbox MCP connection did not create a client session.")

    skills_provider = SkillsProvider(
        MCPSkillsSource(client=_toolbox.session),
        disable_load_skill_approval=True,
        disable_read_skill_resource_approval=True,
    )

    chat_client = FoundryChatClient(
        project_endpoint=endpoint,
        model=model_deployment,
        credential=credential,
    )

    _agent = Agent(
        client=chat_client,
        name="toolbox-agent",
        instructions="You are a customer-support assistant for Contoso Outdoors.",
        context_providers=[skills_provider],
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
        message = " ".join(sys.argv[1:]).strip()
        if not message:
            raise ValueError("Provide a message as a command-line argument.")
        await call_agent_with_toolbox(message)
    finally:
        await close_agent()

asyncio.run(main())
