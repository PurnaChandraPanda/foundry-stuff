"""Persist a prompt agent with native MCP directly to APIM, without a toolbox."""

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPTool, PromptAgentDefinition
from azure.identity import AzureCliCredential

from config import (
    INSTRUCTIONS,
    ProjectSettings,
    allowed_tools,
    https_url,
    load_environment,
    resource_name,
)


def definition() -> PromptAgentDefinition:
    settings = ProjectSettings.from_environment()
    return PromptAgentDefinition(
        model=settings.model,
        instructions=INSTRUCTIONS,
        tools=[
            MCPTool(
                server_label=resource_name("APIM_MCP_SERVER_LABEL"),
                server_url=https_url("APIM_MCP_URL"),
                project_connection_id=resource_name("APIM_MCP_CONNECTION_NAME"),
                allowed_tools=allowed_tools(),
                require_approval="always",
            )
        ],
    )


def main() -> None:
    load_environment()
    settings = ProjectSettings.from_environment()
    agent_definition = definition()
    with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=settings.endpoint, credential=credential) as project,
    ):
        agent = project.agents.create_version(
            agent_name=resource_name("APIM_PROMPT_AGENT_NAME"),
            definition=agent_definition,
        )
    print(f"Created prompt agent: {agent.name}, version: {agent.version}")
    print(f"Set APIM_PROMPT_AGENT_VERSION={agent.version}")
    print("Creation does not prove Foundry can reach APIM. Run run_prompt_agent.py next.")


if __name__ == "__main__":
    main()
