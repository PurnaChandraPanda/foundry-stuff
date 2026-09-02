"""Agent Framework local agent that reaches Fabric IQ through a Foundry toolbox.

Unlike the Fabric data agent tool, Fabric IQ is an MCP server. This attaches the
toolbox published by `create_fabric_iq_toolbox.py` over MCP, so run that first.

Usage:
    python fabric_iq_local_agent.py
    python fabric_iq_local_agent.py --query "how many total trips are there"
    python fabric_iq_local_agent.py --toolbox-version 1
"""

import argparse
import asyncio
import os
import sys

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, FoundryToolbox
from azure.ai.projects import AIProjectClient
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from fabric_iq_config import toolbox_mcp_url

# Fabric responses contain citation markers (e.g. U+3010) that the default
# Windows console encoding (cp1252) cannot encode, which would crash on print.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
MODEL_DEPLOYMENT_NAME = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
TOOLBOX_NAME = os.environ.get("FABRIC_IQ_TOOLBOX_NAME")

INSTRUCTIONS = (
    "You are a helpful assistant with access to your organization's Microsoft Fabric "
    "data through Fabric IQ. Use the Fabric IQ tool for any question about business "
    "data, entities, metrics, or organizational knowledge. Ground every answer in the "
    "data the tool returns and state the numbers you used."
)

DEFAULT_QUERY = "which month had highest travel rides and which month had lowest"


def latest_toolbox_version(credential: AzureCliCredential) -> str:
    """Return the highest published version of the configured toolbox.

    The service happens to list versions newest-first, but versions are compared
    numerically here rather than trusting that ordering.
    """
    if not PROJECT_ENDPOINT:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT is required. Example: "
            "https://<resource>.ai.azure.com/api/projects/<project_name>"
        )

    with AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project:
        try:
            versions = [str(v.version) for v in project.toolboxes.list_versions(TOOLBOX_NAME)]
        except ResourceNotFoundError:
            raise SystemExit(
                f"Toolbox '{TOOLBOX_NAME}' does not exist.\n"
                "Create it first:  python create_fabric_iq_toolbox.py"
            ) from None

    if not versions:
        raise SystemExit(
            f"Toolbox '{TOOLBOX_NAME}' has no versions.\n"
            "Create one:  python create_fabric_iq_toolbox.py"
        )

    numeric = [v for v in versions if v.isdigit()]
    return max(numeric, key=int) if numeric else versions[0]


async def run_agent(credential: AzureCliCredential, version: str, query: str) -> None:
    """Attach the published toolbox over MCP and ask it a question."""
    url = toolbox_mcp_url(PROJECT_ENDPOINT, TOOLBOX_NAME, version)
    print(f"Toolbox: {TOOLBOX_NAME} (version={version})")
    print(f"Toolbox MCP endpoint: {url}")

    # Both are async context managers. Entering them keeps the MCP session's
    # startup and shutdown on the same task - closing implicitly instead raises
    # "Attempted to exit cancel scope in a different task than it was entered in"
    # during interpreter teardown.
    async with (
        FoundryToolbox(credential, url=url) as toolbox_tool,
        Agent(
            # FoundryChatClient resolves the model when it is constructed, so the
            # deployment name belongs here rather than on Agent.
            client=FoundryChatClient(
                project_endpoint=PROJECT_ENDPOINT,
                model=MODEL_DEPLOYMENT_NAME,
                credential=credential,
            ),
            instructions=INSTRUCTIONS,
            tools=[toolbox_tool],
        ) as agent,
    ):
        result = await agent.run(query)
        print(f"Agent: {result.text}")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a local agent against a published Fabric IQ toolbox."
    )
    parser.add_argument(
        "--toolbox-version",
        help="Toolbox version to attach. Defaults to the highest published version.",
    )
    parser.add_argument(
        "--query",
        default=DEFAULT_QUERY,
        help="Question to ask the agent.",
    )
    args = parser.parse_args()

    credential = AzureCliCredential()
    version = args.toolbox_version or latest_toolbox_version(credential)
    await run_agent(credential, version, args.query)


if __name__ == "__main__":
    asyncio.run(main())
