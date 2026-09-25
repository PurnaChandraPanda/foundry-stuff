"""Local MAF orchestration with APIM tool execution in the Foundry toolbox."""

import argparse
import asyncio

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, FoundryToolbox
from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential

from config import (
    INSTRUCTIONS,
    https_url,
    load_environment,
    required,
    resource_name,
    timeout_seconds,
    toolbox_url,
)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", required=True)
    args = parser.parse_args()
    load_environment()
    endpoint = https_url("AZURE_AI_PROJECT_ENDPOINT").rstrip("/")
    model = required("AZURE_AI_MODEL_DEPLOYMENT_NAME")
    url = toolbox_url()
    timeout = timeout_seconds()
    print("APIM calls execute from: Foundry toolbox service, not this machine.")
    with AzureCliCredential() as credential:
        with AIProjectClient(endpoint=endpoint, credential=credential) as project:
            async with Agent(
                name="public-apim-toolbox-maf",
                client=FoundryChatClient(project_endpoint=endpoint, model=model, credential=credential),
                instructions=INSTRUCTIONS,
                tools=[FoundryToolbox(credential, url=url, timeout=float(timeout))],
            ) as agent:
                response = await agent.run(args.query)
                if response.user_input_requests:
                    raise RuntimeError(
                        "This unattended toolbox sample cannot resolve approval or consent requests. "
                        "Review the connection and published toolbox policy before invoking again."
                    )
                print(response.text)


if __name__ == "__main__":
    asyncio.run(main())
