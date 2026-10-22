import asyncio
import os
from datetime import datetime, timezone

from agent_framework import Agent, Message
from agent_framework.anthropic import AnthropicFoundryClient
from anthropic import AsyncAnthropicFoundry
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv

# load environment variables from .env file
load_dotenv()

ENDPOINT = os.getenv("APIM_API_FOUNDRY_ANTHROPIC_ENDPOINT")
DEPLOYMENT_NAME = os.getenv("APIM_API_FOUNDRY_ANTHROPIC_DEPLOYMENT")

def get_current_utc_time() -> str:
    """Return the actual current date and time in UTC."""
    print("[Tool executed] get_current_utc_time")
    return datetime.now(timezone.utc).isoformat()


async def main() -> None:
    with DefaultAzureCredential() as credential:
        token_provider = get_bearer_token_provider(
            credential,
            "https://ai.azure.com/.default",
        )

        async with AsyncAnthropicFoundry(
            base_url=ENDPOINT,
            azure_ad_token_provider=token_provider,
            default_headers={
                    os.getenv("APIM_API_SUBSCRIPTION_KEY_NAME"): os.getenv("APIM_API_SUBSCRIPTION_KEY_VALUE")
                }
        ) as anthropic_client:
            client = AnthropicFoundryClient(
                model=DEPLOYMENT_NAME,
                anthropic_client=anthropic_client,
            )

            # Direct model interaction through Agent Framework.
            response = await client.get_response(
                [
                    Message(
                        "user",
                        contents=["What is the capital of France?"],
                    )
                ],
                options={"max_tokens": 1024},
            )
            print("\nModel response:")
            print(response.text)

            # Agent Framework manages tool invocation and results.
            agent = Agent(
                client=client,
                instructions=(
                    "You are a helpful assistant. "
                    "Always use get_current_utc_time when asked "
                    "for the current date or time. "
                    "Never invent the current time."
                ),
                tools=[get_current_utc_time],
                default_options={"max_tokens": 1024},
            )

            result = await agent.run(
                "Check the current UTC time and tell me "
                "the current date and time in India."
            )
            print("\nAgent response:")
            print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
