"""Persist a prompt agent that calls the public-APIM toolbox through native MCP."""

import argparse

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPTool, PromptAgentDefinition
from azure.identity import AzureCliCredential

from config import (
    INSTRUCTIONS,
    https_url,
    load_environment,
    required,
    resource_name,
    toolbox_url,
)


def definition() -> PromptAgentDefinition:
    return PromptAgentDefinition(
        model=required("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
        instructions=INSTRUCTIONS,
        tools=[
            MCPTool(
                server_label="apim-toolbox",
                server_url=toolbox_url(),
                project_connection_id=resource_name("APIM_TOOLBOX_CONNECTION_NAME"),
                require_approval="always",
            )
        ],
    )


def main() -> None:
    argparse.ArgumentParser(description=__doc__).parse_args()
    load_environment()
    endpoint = https_url("AZURE_AI_PROJECT_ENDPOINT")
    agent_name = resource_name("APIM_PROMPT_AGENT_NAME")
    toolbox_name = resource_name("APIM_TOOLBOX_NAME")
    connection_name = resource_name("APIM_TOOLBOX_CONNECTION_NAME")
    url = toolbox_url()
    agent_definition = definition()
    with (
        AzureCliCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project,
    ):
        toolbox = project.toolboxes.get(name=toolbox_name)
        if not toolbox.default_version:
            raise ValueError("The toolbox has no default version. Publish/promote a version first.")
        connection = project.connections.get(name=connection_name, include_credentials=False)
        if connection.target != url:
            raise ValueError(
                "APIM_TOOLBOX_CONNECTION_NAME must target the exact toolbox consumer URL "
                f"{url}, not the downstream APIM MCP URL."
            )
        agent = project.agents.create_version(
            agent_name=agent_name,
            definition=agent_definition,
        )
    print(f"Created prompt agent: {agent.name}, version: {agent.version}")
    print(f"Set APIM_PROMPT_AGENT_VERSION={agent.version}")
    print(f"Toolbox: {toolbox_name}, current default version: {toolbox.default_version}")
    print("The toolbox consumer endpoint follows future default-version promotions.")
    if agent.instance_identity is not None:
        print(f"Agent identity principal ID: {agent.instance_identity.principal_id}")
    print("Grant the connection's runtime identity Foundry User access on the toolbox project.")
    print("Creation does not prove tool access. Run run_prompt_agent.py and verify an MCP call.")


if __name__ == "__main__":
    main()
