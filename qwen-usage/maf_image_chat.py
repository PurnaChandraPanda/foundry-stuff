# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from urllib.request import urlopen

from agent_framework import Agent, Content
from agent_framework.openai import OpenAIChatCompletionClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

IMAGE_URL = "https://suanli.cn/assets/QucgbCSISoA7XCxlEI9cVQSOnbd.png"


def download_image(url: str) -> bytes:
    with urlopen(url, timeout=30) as response:
        return response.read()

# Load environment variables from .env file
load_dotenv()

"""
OpenAI Chat Client Image Analysis Example

This sample demonstrates using OpenAI Chat Client for image analysis and vision tasks,
showing multi-modal content handling with text and images.
"""


async def main():
    print("=== OpenAI Chat Client Agent with Image Analysis ===")

    token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")

    # 1. Create an OpenAI Chat agent with vision capabilities
    agent = Agent(
        client=OpenAIChatCompletionClient(
            base_url=os.environ["OPENAI_BASE_URL"],
            model=os.environ["FOUNDRY_MODELS_ENDPOINT"],
            credential=token_provider,
        ),
        name="VisionAgent",
        instructions="Analyze the provided image and describe what you see.",
    )

    # 2. Get the agent's response
    print("User: What do you see in this image? [Image provided]")
    image_data = await asyncio.to_thread(download_image, IMAGE_URL)
    result = await agent.run(Content.from_data(image_data, media_type="image/png"))
    print(f"Agent: {result.text}")


if __name__ == "__main__":
    asyncio.run(main())
