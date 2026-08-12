import base64
import os
from urllib.request import urlopen

from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from qwen_agent.agents import Assistant
from qwen_agent.llm.schema import ContentItem, Message

IMAGE_URL = "https://suanli.cn/assets/QucgbCSISoA7XCxlEI9cVQSOnbd.png"
FOUNDRY_SCOPE = "https://ai.azure.com/.default"


def image_as_data_uri(url: str) -> str:
    with urlopen(url, timeout=30) as response:
        image_data = response.read()
    encoded_image = base64.b64encode(image_data).decode("ascii")
    return f"data:image/png;base64,{encoded_image}"


def main() -> None:
    load_dotenv()

    access_token = DefaultAzureCredential().get_token(FOUNDRY_SCOPE).token
    agent = Assistant(
        llm={
            "model_type": "qwenvl_oai",
            "model": os.environ["FOUNDRY_MODELS_ENDPOINT"],
            "model_server": os.environ["OPENAI_BASE_URL"],
            "api_key": access_token,
        },
        system_message="Analyze the provided image and describe what you see.",
        name="VisionAgent",
    )

    messages = [
        Message(
            role="user",
            content=[
                ContentItem(image=image_as_data_uri(IMAGE_URL)),
                ContentItem(text="What do you see in this image?"),
            ],
        )
    ]
    responses = agent.run_nonstream(messages)
    print(f"Agent: {responses[-1].content}")


if __name__ == "__main__":
    main()
