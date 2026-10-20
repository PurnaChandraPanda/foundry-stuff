
import argparse
from html import parser
import os

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from dotenv import load_dotenv

load_dotenv()

def main() -> None:
    print("Call the BYOM prompt agent.")

    endpoint = os.environ.get("PROJECT_ENDPOINT")
    agent_name = os.environ.get("PROMPT_AGENT_NAME")
    prompt = "Say hello in five words."
    
    project = AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())
    
    # 2) Invoke it through the Responses API (NOT threads/runs).
    client = project.get_openai_client()
    conversation = client.conversations.create()
    response = client.responses.create(
        conversation=conversation.id,
        input=prompt,
        extra_body={"agent_reference": {"name": agent_name, "type": "agent_reference"}},
    )

    print("-" * 60)
    print(response.output_text)
    print("-" * 60)


if __name__ == "__main__":
    main()