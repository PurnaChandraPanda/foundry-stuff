import os
from dotenv import load_dotenv

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient

load_dotenv()

PROJECT_ENDPOINT = os.environ["FOUNDRY_PROJECT_ENDPOINT"]

# Agent details
AGENT_NAME = os.environ.get("FOUNDRY_AGENT_NAME")

project_client = AIProjectClient(
    endpoint=PROJECT_ENDPOINT,
    credential=DefaultAzureCredential(),
)

agent_name = AGENT_NAME

# Get the OpenAI client from the project client
openai_client = project_client.get_openai_client()

def main(user_input: str):
    # Optional Step: Create a conversation to use with the agent
    conversation = openai_client.conversations.create()
    print(f"Created conversation (id: {conversation.id})")

    # Create a conversation to use with the agent
    stream_response = openai_client.responses.create(
        stream=True,
        tool_choice="required",
        input=user_input,
        conversation=conversation.id,
        extra_body={"agent_reference": {"name": AGENT_NAME, "type": "agent_reference"}},
        )
    
    # Review the event stream response
    for event in stream_response:
        if event.type == "response.created":
            print(f"Follow-up response created with ID: {event.response.id}")
        elif event.type == "response.output_text.delta":
            print(event.delta, end="", flush=True)
        elif event.type == "response.text.done":
            print(f"\nFollow-up response done!")
        elif event.type == "response.output_item.done":
            if event.item.type == "message":
                item = event.item
                if item.content[-1].type == "output_text":
                    text_content = item.content[-1]
                    for annotation in text_content.annotations:
                        if annotation.type == "url_citation":
                            print(
                                f"URL Citation: {annotation.url}, "
                                f"Start index: {annotation.start_index}, "
                                f"End index: {annotation.end_index}"
                            )
                        
        elif event.type == "response.completed":
            print(f"\nFollow-up completed!")
            print(f"Agent response: {event.response.output_text}")

if __name__ == "__main__":
    user_input = "Show me the latest London Underground service updates"
    main(user_input)

