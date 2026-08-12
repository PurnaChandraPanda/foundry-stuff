import os

from qwen_agent.agents import Assistant
from qwen_agent.llm.schema import ContentItem, Message

from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

FOUNDRY_SCOPE = "https://ai.azure.com/.default"

def main() -> None:
    load_dotenv()

    access_token = DefaultAzureCredential().get_token(FOUNDRY_SCOPE).token
    agent = Assistant(
        llm={
            # supply correct model_type value for qwen_agent to honor interaction modality
            "model_type": "oai",
            "model": os.environ["FOUNDRY_MODELS_ENDPOINT"],
            "model_server": os.environ["OPENAI_BASE_URL"],
            "api_key": access_token,
        },
        system_message="You are a helpful assistant.",
        name="TestAgent",
    )

    messages = [
        Message(
            role="user",
            content=[
                # pass the user prompt as text content
                ContentItem(text="hello"),
            ],
        )
    ]
    responses = agent.run_nonstream(messages)
    print(f"Agent: {responses[-1].content}")
    # print(responses)


if __name__ == "__main__":
    main()
