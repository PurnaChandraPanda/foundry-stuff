import os

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, SkillReferenceParam
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv("../../src/agent-framework-agent-foundry-skills-responses/.env")

# Populate the agent required parameters from env file
endpoint          = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
model_deployment  = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
agent_name        = "contoso-support-agent"

# Read foundry skill names from env file and split them into a list
skill_names = [
    name.strip()
    for name in os.environ["SKILL_NAMES"].split(",")
    if name.strip()
]

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as project_client,
):
    # Resolve Foundry skill names to skill IDs.
    available = {skill.name: skill for skill in project_client.beta.skills.list()}

    missing = [name for name in skill_names if name not in available]
    if missing:
        raise RuntimeError(f"Foundry skills not found: {missing}")

    skill_tools = [
        SkillReferenceParam(
            skill_id=available[name].id,
            version=available[name].default_version,
        )
        for name in skill_names
    ]
    
    # Create a prompt agent mapped to the Foundry skills.
    agent = project_client.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model_deployment,
            instructions=(
                "You are a helpful assistant"
            ),
            tools=skill_tools,
        ),
    )

    print(f"Created agent -> name={agent.name}, version={agent.version}, id={agent.id}")