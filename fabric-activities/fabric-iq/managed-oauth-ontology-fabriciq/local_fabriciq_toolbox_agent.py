"""Agent Framework local agent that reaches Fabric IQ through a Foundry toolbox.

Unlike the Fabric data agent tool, Fabric IQ is an MCP server. This attaches the
toolbox published by `create_fabric_iq_toolbox.py` over MCP, so run that first.

Usage:
    python local_fabriciq_toolbox_agent.py
    python local_fabriciq_toolbox_agent.py --query "Describe MovieRating."
    python local_fabriciq_toolbox_agent.py --toolbox-version 1
"""

import argparse
import asyncio
import os
import sys

from agent_framework import Agent
from agent_framework.exceptions import ToolException
from agent_framework.foundry import FoundryChatClient, FoundryToolbox
from azure.ai.projects import AIProjectClient
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential
from mcp.shared.exceptions import McpError

from fabric_iq_config import toolbox_mcp_url
from fabric_iq_oauth import CONSENT_GUIDANCE, load_environment, report_oauth_error, required_env

# Fabric responses contain citation markers (e.g. U+3010) that the default
# Windows console encoding (cp1252) cannot encode, which would crash on print.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

load_environment()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
TOOLBOX_NAME = os.environ.get("FABRIC_IQ_TOOLBOX_NAME")

INSTRUCTIONS = (
    "You are a helpful assistant with access to your organization's Microsoft Fabric "
    "data through Fabric IQ. Use the Fabric IQ tool for any question about business "
    "data, entities, metrics, or organizational knowledge. Ground every answer in the "
    "data the tool returns. Discover canonical entity names before filtering. "
    "Do not claim metadata is row data. If consent is required, report the "
    "actual consent request; do not present it as an empty dataset."
)

DEFAULT_QUERY = "Describe MovieRating using the ontology entity metadata tool."


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

    toolbox_name = required_env("FABRIC_IQ_TOOLBOX_NAME")
    with AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project:
        try:
            versions = [str(v.version) for v in project.toolboxes.list_versions(toolbox_name)]
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
    endpoint = required_env("AZURE_AI_PROJECT_ENDPOINT")
    url = toolbox_mcp_url(endpoint, required_env("FABRIC_IQ_TOOLBOX_NAME"), version)
    print(f"Toolbox: {TOOLBOX_NAME} (version={version})")
    print(f"Toolbox MCP endpoint: {url}")

    async with FoundryToolbox(credential, url=url) as toolbox_tool:
        names = [tool.name for tool in toolbox_tool.functions]
        if not names:
            raise RuntimeError("The toolbox exposed no tools. Run diagnose_fabric_iq_connection.py.")
        print(f"Available toolbox tools: {', '.join(names)}")
        async with Agent(
            client=FoundryChatClient(
                project_endpoint=endpoint,
                model=required_env("AZURE_AI_MODEL_DEPLOYMENT_NAME"),
                credential=credential,
            ),
            instructions=INSTRUCTIONS,
            tools=[toolbox_tool],
        ) as agent:
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

    with AzureCliCredential(tenant_id=required_env("TENANT_ID")) as credential:
        version = args.toolbox_version or latest_toolbox_version(credential)
        await run_agent(credential, version, args.query)


if __name__ == "__main__":
    exit_code = 0
    try:
        asyncio.run(main())
    except* (McpError, ToolException) as errors:
        report_oauth_error(errors)
        print(CONSENT_GUIDANCE, file=sys.stderr)
        exit_code = 1
    sys.exit(exit_code)
