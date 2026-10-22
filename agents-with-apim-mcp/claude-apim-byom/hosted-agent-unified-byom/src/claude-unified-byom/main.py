import asyncio
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from dotenv import load_dotenv

# load environment variables from the .env file
load_dotenv()

def required_setting(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"Set {name} in the environment or the adjacent .env file.")
    return value


async def run() -> None:    
    endpoint = required_setting("FOUNDRY_PROJECT_ENDPOINT")
    model = required_setting("BYOM_MODEL")

    async with (
        DefaultAzureCredential() as credential,
        AIProjectClient(endpoint=endpoint, credential=credential) as project,
    ):
        foundry_client = FoundryChatClient(project_client=project, model=model)
        async with foundry_client.client:
            agent = Agent(
                client=foundry_client,
                instructions="You are a helpful assistant.",
                default_options={"store": False},
            )

            # Start the Responses HTTP server to host the agent
            server = ResponsesHostServer(agent)
            await server.run_async()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()