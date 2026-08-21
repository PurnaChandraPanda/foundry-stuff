import os
from dotenv import load_dotenv

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    A2APreviewTool,
)

load_dotenv()

# Read the environment variables for the Foundry project endpoint, agent name, and A2A connection name
PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
A2A_CONNECTION_NAME = os.getenv("FOUNDRY_A2A_CONNECTION_NAME")
AGENT_NAME = os.getenv("FOUNDRY_CALLER_AGENT_NAME")

project = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)

# get tehe A2A connection from the project
a2a_connection = project.connections.get(A2A_CONNECTION_NAME)

tool = A2APreviewTool(
    project_connection_id=a2a_connection.id,
    send_credentials_for_agent_card=True,
)

# Create a new version of the agent with the A2A tool
agent = project.agents.create_version(
    agent_name=AGENT_NAME,
    definition=PromptAgentDefinition(
        model=os.getenv("FOUNDRY_CALLER_MODEL_NAME"),
        instructions=(
            "You are a helpful assistant. Use the A2A tool "
            "to delegate tasks to the target agent."
        ),
        tools=[tool],
    ),
)

print(f"Agent created (id: {agent.id}, name: {agent.name}, version: {agent.version})")
