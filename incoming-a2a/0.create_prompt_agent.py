"""
DESCRIPTION:
    This sample demonstrates how to run Prompt Agent operations
    using the Web Search Tool and a synchronous client.

USAGE:
    python sample_agent_web_search.py

    Before running the sample:

    pip install "azure-ai-projects>=2.0.0" python-dotenv

    Set these environment variables with your own values:
    1) FOUNDRY_PROJECT_ENDPOINT - The Azure AI Project endpoint, as found in the Overview
       page of your Microsoft Foundry portal.
    2) FOUNDRY_MODEL_NAME - The deployment name of the AI model, as found under the "Name" column in
       the "Models + endpoints" tab in your Microsoft Foundry project.
    3) FOUNDRY_AGENT_NAME - The name of the AI agent.
"""

import os
from dotenv import load_dotenv

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import (
    PromptAgentDefinition,
    WebSearchTool,
    WebSearchApproximateLocation,
)

load_dotenv()

endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
agent_name = os.environ.get("FOUNDRY_AGENT_NAME")

tool = WebSearchTool(user_location=WebSearchApproximateLocation(country="GB", city="London", region="London"))

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client,
):
    try:
        created_version = project_client.agents.create_version(
            agent_name=agent_name,
            definition=PromptAgentDefinition(
                        model=os.environ["FOUNDRY_MODEL_NAME"],
                        instructions="You are a helpful assistant that can search the web",
                        tools=[tool],
            ),
            description="Agent for web search.",
        )
        print(
            f"Agent created (id: {created_version.id}, name: {created_version.name}, version: {created_version.version})"
        )
    except Exception as e:
        print(f"Failed to create agent: {e}")
        exit(1)

