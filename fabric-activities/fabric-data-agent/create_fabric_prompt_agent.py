import os

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    FabricDataAgentToolParameters,
    MicrosoftFabricPreviewTool,
    PromptAgentDefinition,
    ToolProjectConnection,
)
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# load environment variables from .env file
load_dotenv()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
FABRIC_CONNECTION_NAME = os.environ.get("FABRIC_CONNECTION_NAME")
MODEL_DEPLOYMENT_NAME = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
AGENT_NAME = os.environ.get("FABRIC_AGENT_NAME")


def get_fabric_connection_id(project: AIProjectClient) -> str:
    # read from the project connections using the connection name
    return project.connections.get(FABRIC_CONNECTION_NAME).id


def create_fabric_prompt_agent(project: AIProjectClient, connection_id: str):
    return project.agents.create_version(
        agent_name=AGENT_NAME,
        definition=PromptAgentDefinition(
            model=MODEL_DEPLOYMENT_NAME,
            instructions=(
                "You are a helpful assistant. Use the Microsoft Fabric data agent to answer "
                "questions about the connected enterprise data."
            ),
            tools=[
                MicrosoftFabricPreviewTool(
                    fabric_dataagent_preview=FabricDataAgentToolParameters(
                        project_connections=[
                            ToolProjectConnection(project_connection_id=connection_id)
                        ]
                    )
                )
            ],
        ),
    )


def main() -> None:
    if not PROJECT_ENDPOINT:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT is required. Example: "
            "https://<resource>.ai.azure.com/api/projects/<project_name>"
        )

    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=DefaultAzureCredential(),
    )

    connection_id = get_fabric_connection_id(project)
    print(f"Using connection id: {connection_id}")
    agent = create_fabric_prompt_agent(project, connection_id)

    print(f"Created agent: {agent.name} (version={agent.version}, id={agent.id})")
    print(f"Use this agent name in run_fabric_prompt_agent.py: {agent.name}")


if __name__ == "__main__":
    main()
