import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, MCPTool, MCPToolboxTool
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv("../../src/agent-framework-agent-with-foundry-toolbox-responses/.env")

# Populate the agent required parameters from env file
endpoint          = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
model_deployment  = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
agent_name        = "ado-toolbox-prompt-agent"          # <-- shared key between the two files
toolbox_url      = os.environ["TOOLBOX_ENDPOINT"]


ado_toolbox_conn_name = "ado-toolbox-conn"
ado_toolbox_conn_id = f"{os.environ['FOUNDRY_PROJECT_ID']}/connections/{ado_toolbox_conn_name}"

# Define the ADO toolbox tool for the agent. This is a simple wrapper around the MCP endpoint that allows the agent to call tools in the toolbox.
ado_tool = MCPTool(
    server_label="ado",                 # tool-call identifier (no spaces)
    server_url=toolbox_url,
    project_connection_id=ado_toolbox_conn_id,   # auth resolved from the project connection
    headers={"Foundry-Features": "Toolboxes=V1Preview"},  # toolbox still needs this flag
    require_approval="never",
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
            instructions="You are a helpful assistant with access to Azure DevOps tools via the ADO toolbox.",
            tools=[ado_tool],
        ),
    )
    print(f"Created agent -> name={agent.name}, version={agent.version}, id={agent.id}")