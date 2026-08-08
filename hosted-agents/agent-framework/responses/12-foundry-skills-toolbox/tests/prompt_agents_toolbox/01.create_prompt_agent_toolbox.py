import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, MCPTool, MCPToolboxTool
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv("../../src/agent-framework-agent-foundry-skills-responses/.env")

# Populate the agent required parameters from env file
endpoint          = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
model_deployment  = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
agent_name        = "contoso-support-agent"          # <-- shared key between the two files
toolbox_url      = os.environ["TOOLBOX_ENDPOINT"]

# Define the toolbox tool for the agent. This is a simple wrapper around the MCP endpoint that allows the agent to call skills wrapped in the toolbox.
_tool = MCPTool(
    server_label="skill_toolbox",                 # tool-call identifier (no spaces)
    server_url=toolbox_url,
    headers={"Foundry-Features": "Toolboxes=V1Preview"},  # toolbox still needs this flag
    require_approval="never",
    project_connection_id=(
        f"{os.environ['FOUNDRY_PROJECT_ID']}"
        "/connections/contoso-skills-toolbox-conn"
    ),
    # allowed_tools=["repo_search_commits", "core_list_projects"],  # optional allow-list
)


with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
):
    agent = project_client.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model_deployment,
            instructions="You are a helpful assistant.",
            tools=[_tool],
        ),
    )
    print(f"Created agent -> name={agent.name}, version={agent.version}, id={agent.id}")