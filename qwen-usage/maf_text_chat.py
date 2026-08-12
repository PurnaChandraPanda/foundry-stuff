# Copyright (c) Microsoft. All rights reserved.

import asyncio
import os
from urllib.request import urlopen

from agent_framework import Agent, Content
from agent_framework.openai import OpenAIChatCompletionClient
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv


# Load environment variables from .env file
load_dotenv()

async def main():
    print("=== OpenAI Chat Client Agent ===")

    token_provider = get_bearer_token_provider(DefaultAzureCredential(), "https://ai.azure.com/.default")

    # 1. Create an OpenAI Chat agent 
    agent = Agent(
        client=OpenAIChatCompletionClient(
            base_url=os.environ["OPENAI_BASE_URL"],
            model=os.environ["FOUNDRY_MODELS_ENDPOINT"],
            credential=token_provider,
        ),
        name="TestAgent",
        instructions="You are a helpful assistant.",
    )

    # 2. Get the agent's response
    input_prompt = "hello"
    print(f"User: {input_prompt}")
    result = await agent.run(Content.from_text(input_prompt))
    print(f"Agent: {result.text}")

    # capture token usage details if available
    usage = getattr(result, "usage_details", None)
    if usage:
        print(f"Token usage: {usage}")
        if isinstance(usage, dict):
            input_tokens = usage.get("input_token_count", usage.get("prompt_tokens"))
            output_tokens = usage.get("output_token_count", usage.get("completion_tokens"))
            total_tokens = usage.get("total_token_count", usage.get("total_tokens"))
            print(
                "Usage summary: "
                f"input={input_tokens}, output={output_tokens}, total={total_tokens}"
            )
    else:
        print("Token usage: unavailable")
    

if __name__ == "__main__":
    asyncio.run(main())
