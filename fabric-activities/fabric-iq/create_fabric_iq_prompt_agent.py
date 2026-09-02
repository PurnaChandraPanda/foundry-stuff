"""Create a Foundry prompt agent that answers questions through the Fabric IQ tool.

Fabric IQ is reached over MCP, so this attaches `FabricIQPreviewTool` pointing at a
`RemoteTool` project connection. Create that connection first with
`create_fabric_iq_connection.sh`.

Run `run_fabric_iq_prompt_agent.py` afterwards to query the agent.
"""

import os

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FabricIQPreviewTool, PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from fabric_iq_config import resolve_item_type, resolve_server_url

load_dotenv()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
CONNECTION_NAME = os.environ.get("FABRIC_IQ_CONNECTION_NAME")
MODEL_DEPLOYMENT_NAME = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
AGENT_NAME = os.environ.get("FABRIC_IQ_AGENT_NAME")
SERVER_LABEL = os.environ.get("FABRIC_IQ_SERVER_LABEL")

# Derived from FABRIC_IQ_ITEM_TYPE plus the workspace/item GUIDs.
SERVER_URL = resolve_server_url()

# The model only calls the tool when it recognizes the question as a data question,
# so name the domain explicitly rather than saying "use tools when helpful".
INSTRUCTIONS = (
    "You are a helpful assistant with access to your organization's Microsoft Fabric "
    "data through Fabric IQ. Use the Fabric IQ tool for any question about business "
    "data, entities, metrics, or organizational knowledge. Ground every answer in the "
    "data the tool returns and state the numbers you used."
)


def get_connection_id(project: AIProjectClient) -> str:
    return project.connections.get(CONNECTION_NAME).id


def create_fabric_iq_prompt_agent(project: AIProjectClient, connection_id: str):
    # server_label and server_url are optional: when omitted, the endpoint stored on
    # the project connection is used. They are passed here so the agent definition is
    # self-describing and the approval prompt shows a readable label.
    tool = FabricIQPreviewTool(
        project_connection_id=connection_id,
        # Without this the tool defaults to "always", which stalls a non-interactive
        # script waiting for an approval that never arrives.
        require_approval="never",
    )
    if SERVER_LABEL:
        tool.server_label = SERVER_LABEL
    if SERVER_URL:
        tool.server_url = SERVER_URL

    return project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
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

    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    connection_id = get_connection_id(project)
    print(f"Using connection id: {connection_id}")
    print(f"Item type: {resolve_item_type()}")
    print(f"Server URL: {SERVER_URL}")
    agent = create_fabric_iq_prompt_agent(project, connection_id)

    print(f"Created agent: {agent.name} (version={agent.version}, id={agent.id})")
    print(f"Use this agent name in run_fabric_iq_prompt_agent.py: {agent.name}")


if __name__ == "__main__":
    main()
