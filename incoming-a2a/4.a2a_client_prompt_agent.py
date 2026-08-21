import asyncio
import httpx
import os
from dotenv import load_dotenv

from azure.identity import DefaultAzureCredential
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import new_text_message
from a2a.types.a2a_pb2 import (
    Role,
    SendMessageRequest,
)

load_dotenv()

# Your Foundry agent's A2A base path
A2A_BASE_URL = (
    f"{os.getenv('FOUNDRY_PROJECT_ENDPOINT')}"
    f"/agents/{os.getenv('FOUNDRY_AGENT_NAME')}/endpoint/protocols/a2a"
)
# Agent card path, relative to the A2A base URL.
AGENT_CARD_PATH = "agentCard/v1.0"


async def main():
    # Get a Microsoft Entra token
    credential = DefaultAzureCredential()
    token = credential.get_token("https://ai.azure.com/.default").token

    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx.Timeout(120.0),
    ) as httpx_client:
        # Resolve the agent card from the custom path
        resolver = A2ACardResolver(
            httpx_client=httpx_client,
            base_url=A2A_BASE_URL,
            agent_card_path=AGENT_CARD_PATH,
        )
        agent_card = await resolver.get_agent_card()

        # Create a non-streaming A2A client
        config = ClientConfig(
            streaming=False,
            httpx_client=httpx_client,
        )
        client = await create_client(
            agent=agent_card, client_config=config
        )

        # Send a message to the Foundry agent
        message = new_text_message(
            "Hello, what can you do?", role=Role.ROLE_USER
        )
        request = SendMessageRequest(message=message)

        async for response in client.send_message(request):
            print(response)

        await client.close()


if __name__ == "__main__":
    asyncio.run(main())