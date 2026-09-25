"""Local MAF agent with code-executed MCP directly to private APIM."""

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework.foundry import FoundryChatClient
from azure.core.credentials import TokenCredential

from config import (
    INSTRUCTIONS,
    ProjectSettings,
    allowed_tools,
    apim_headers,
    https_url,
    resource_name,
    timeout_seconds,
)


def build_agent(credential: TokenCredential) -> Agent:
    settings = ProjectSettings.from_environment()
    headers = apim_headers()
    tool = MCPStreamableHTTPTool(
        name=resource_name("APIM_MCP_SERVER_LABEL"),
        url=https_url("APIM_MCP_URL"),
        header_provider=lambda _: dict(headers),
        allowed_tools=allowed_tools(),
        load_prompts=False,
        approval_mode="always_require",
        request_timeout=timeout_seconds(),
    )
    # Connect only inside the runner's event loop, not in a temporary startup loop.
    return Agent(
        name="private-apim-maf",
        client=FoundryChatClient(
            project_endpoint=settings.endpoint,
            model=settings.model,
            credential=credential,
        ),
        instructions=INSTRUCTIONS,
        tools=[tool],
    )
