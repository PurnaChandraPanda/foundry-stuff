import os
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

SAMPLE_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = SAMPLE_ROOT / "src" / "agent-framework-agent-with-skills-responses"
SKILL_FILE = SOURCE_ROOT / "skills" / "travel-guide" / "SKILL.md"
load_dotenv(SOURCE_ROOT / ".env")

endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
model_deployment = os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"]
agent_name = "local-travel-guide-prompt-agent"

skill_instructions = SKILL_FILE.read_text(encoding="utf-8")
instructions = f"""You are a helpful travel planning assistant.

Follow the local skill instructions below, except do not attempt to run its local
Python script. Prompt agents cannot execute local files. Produce the requested
travel guide directly as a well-structured text response.

## Local travel-guide skill

{skill_instructions}
"""

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
):
    agent = project_client.agents.create_version(
        agent_name=agent_name,
        definition=PromptAgentDefinition(
            model=model_deployment,
            instructions=instructions,
        ),
    )
    print(f"Created agent -> name={agent.name}, version={agent.version}, id={agent.id}")
