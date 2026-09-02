import asyncio
import os
import sys

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

# Fabric responses contain citation markers (e.g. U+3010) that the default
# Windows console encoding (cp1252) cannot encode, which would crash on print.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# load environment variables from .env file
load_dotenv()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
FABRIC_CONNECTION_NAME = os.environ.get("FABRIC_CONNECTION_NAME")
MODEL_DEPLOYMENT_NAME = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")

QUERY = "which month had highest travel rides and which month had lowest"

async def main() -> None:
    if not PROJECT_ENDPOINT:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT is required. Example: "
            "https://<resource>.ai.azure.com/api/projects/<project_name>"
        )

    credential = AzureCliCredential()
    project = AIProjectClient(
        endpoint=PROJECT_ENDPOINT,
        credential=credential,
    )

    # read the connection ID from the project connections using the connection name
    connection_id = project.connections.get(FABRIC_CONNECTION_NAME).id

    # Pass the tool as a plain dict. agent_framework_foundry sanitizes hosted
    # tools with a shallow dict(), which leaves the nested
    # FabricDataAgentToolParameters as an Azure model object and fails with
    # "Object of type FabricDataAgentToolParameters is not JSON serializable".
    # as_dict() serializes the whole tree.
    fabric_tool = FoundryChatClient.get_fabric_tool(connection_id=connection_id).as_dict()

    agent = Agent(
        # FoundryChatClient resolves the model at construction time, so it must
        # be passed here (or via FOUNDRY_MODEL); setting it only on Agent raises
        # "Model is required."
        # project_endpoint must be passed explicitly: the client only reads the
        # FOUNDRY_PROJECT_ENDPOINT env var, not AZURE_AI_PROJECT_ENDPOINT.
        client=FoundryChatClient(
            project_endpoint=PROJECT_ENDPOINT,
            model=MODEL_DEPLOYMENT_NAME,
            credential=credential,
            allow_preview=True,
        ),
        instructions=(
            "You are a helpful assistant. Use the connected Microsoft Fabric data agent "
            "to answer questions about enterprise data."
        ),
        tools=[fabric_tool],
    )

    result = await agent.run(QUERY)
    print(f"Agent: {result.text}")


if __name__ == "__main__":
    asyncio.run(main())
