import os
import sys
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

SAMPLE_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = SAMPLE_ROOT / "src" / "agent-framework-agent-with-skills-responses"
load_dotenv(SOURCE_ROOT / ".env")

endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
agent_name = "local-travel-guide-prompt-agent"
message = " ".join(sys.argv[1:]).strip()
if not message:
    message = "Create a 3-day Lisbon travel guide focused on food and viewpoints."

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
):
    openai = project_client.get_openai_client(agent_name=agent_name)
    response = openai.responses.create(input=message)
    print(response.output_text)
