import os
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from dotenv import load_dotenv
from openai import project

# Load environment variables from .env file
load_dotenv("../../src/agent-framework-agent-with-foundry-toolbox-responses/.env")

endpoint          = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
agent_name        = "ado-tools-prompt-agent"          # <-- shared key between the two files

with (
    DefaultAzureCredential() as credential,
    AIProjectClient(endpoint=endpoint, credential=credential) as project_client
):
    # define user prompt    
    message = "hi"

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
    message = "List recent 3 commits in project 'wfm-proxy', repo 'wfm-proxy', branch 'master'."

    # Ask a follow-up question in the same conversation
    response = openai.responses.create(
        conversation=conversation.id,
        input=message,
    )
    print(response.output_text)