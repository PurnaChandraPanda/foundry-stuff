import os
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv("../../src/agent-framework-agent-foundry-skills-responses/.env")

# Populate the agent required parameters from env file
endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
agent_name = "contoso-support-agent"

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential, allow_preview=True) as project_client
):
    # define user prompt    
    message = (
        "I want a $750 refund on Order #A-1042 right now "
        "or I am calling my lawyer."
    )

    # Get an OpenAI client pre-bound to the specified agent
    openai = project_client.get_openai_client(agent_name=agent_name)

    # Create a conversation for multi-turn chat
    conversation = openai.conversations.create()

    # Reference the agent to get a response
    response = openai.responses.create(
        conversation=conversation.id,
        input=message,
    )

    print(f"Response output: {response.output_text}")

    # follow up prompt to the same conversation
    message = "Hi, I am Alex. I just want to confirm I can return my tent within 30 days."

    # Ask a follow-up question in the same conversation
    response = openai.responses.create(
        conversation=conversation.id,
        input=message,
    )
    print(response.output_text)