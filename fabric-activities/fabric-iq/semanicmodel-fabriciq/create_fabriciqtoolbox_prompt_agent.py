"""Create a Foundry prompt agent that reaches Fabric IQ through a published toolbox.

The agent attaches the toolbox MCP endpoint as an MCP tool. Publishing the toolbox
separately keeps the Fabric IQ UserEntraToken connection and toolbox version explicit.
"""

import argparse
import os

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPTool, PromptAgentDefinition
from azure.identity import AzureCliCredential

from azure.core.exceptions import ResourceNotFoundError
from fabric_iq_config import resolve_item_type, toolbox_mcp_url
from fabric_iq_oauth import load_environment, required_env, verify_user_entra_connection

load_environment()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
CONNECTION_NAME = os.environ.get("FABRIC_IQ_CONNECTION_NAME")
SERVER_LABEL = os.environ.get("FABRIC_IQ_TOOLBOX_SERVER_LABEL")
TOOLBOX_NAME = os.environ.get("FABRIC_IQ_TOOLBOX_NAME")
TOOLBOX_AGENT_NAME = os.environ.get("FABRIC_IQ_TOOLBOX_AGENT_NAME")

# The model only calls the tool when it recognizes the question as a data question,
# so name the domain explicitly rather than saying "use tools when helpful".
INSTRUCTIONS = (
    "You are a helpful assistant with access to your organization's Microsoft Fabric "
    "data through Fabric IQ. Use the Fabric IQ tool for any question about business "
    "data, entities, metrics, or organizational knowledge. Ground every answer in the "
    "data the tool returns and state the numbers you used. For Power BI semantic-model "
    "questions, resolve the semantic model, inspect its schema, and call ExecuteQuery "
    "with a valid DAX EVALUATE statement. Use the tool's returned content, not only "
    "artifact citations."
)


def create_fabric_iq_prompt_agent(project: AIProjectClient, toolbox_url: str):
    tool = MCPTool(
        server_label=SERVER_LABEL,
        server_url=toolbox_url,
        require_approval="never",
    )

    return project.agents.create_version(
        agent_name=TOOLBOX_AGENT_NAME,
        definition=PromptAgentDefinition(
            model=required_env("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
            instructions=INSTRUCTIONS,
            tools=[tool],
        ),
    )


def main() -> None:
    if not PROJECT_ENDPOINT:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT is required. Example: "
            "https://<resource>.ai.azure.com/api/projects/<project_name>"
        )
    if not CONNECTION_NAME:
        raise ValueError("FABRIC_IQ_CONNECTION_NAME is required.")
    if not TOOLBOX_NAME:
        raise ValueError("FABRIC_IQ_TOOLBOX_NAME is required.")

    with (
        AzureCliCredential(tenant_id=required_env("TENANT_ID")) as credential,
        AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project,
    ):
        connection_id = verify_user_entra_connection(credential)
        try:
            toolbox = project.toolboxes.get_version(
                name=required_env("FABRIC_IQ_TOOLBOX_NAME"),
                version=required_env("FABRIC_IQ_TOOLBOX_VERSION"),
            )
        except ResourceNotFoundError:
            raise SystemExit(
                f"Toolbox '{required_env('FABRIC_IQ_TOOLBOX_NAME')}' "
                f"version '{required_env('FABRIC_IQ_TOOLBOX_VERSION')}' was not found."
            ) from None

        if not any(
            tool.get("type") == "fabric_iq_preview"
            and tool.get("project_connection_id") == connection_id
            for tool in toolbox.as_dict().get("tools", [])
        ):
            raise ValueError(
                "The toolbox version does not reference the configured "
                "UserEntraToken connection."
            )

        toolbox_url = toolbox_mcp_url(
            required_env("AZURE_AI_PROJECT_ENDPOINT"),
            required_env("FABRIC_IQ_TOOLBOX_NAME"),
            required_env("FABRIC_IQ_TOOLBOX_VERSION"),
        )
        print(f"Using connection id: {connection_id}")
        print(f"Item type: {resolve_item_type()}")
        print(f"Toolbox URL: {toolbox_url}")
        agent = create_fabric_iq_prompt_agent(project, toolbox_url)

    print(f"Created agent: {agent.name} (version={agent.version}, id={agent.id})")
    print(
        "Use this agent name in run_fabriciqtoolbox_prompt_agent.py: "
        f"{agent.name}"
    )


if __name__ == "__main__":
    main()
