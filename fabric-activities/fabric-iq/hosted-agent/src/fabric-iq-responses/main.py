"""Foundry hosted agent that answers questions through a Fabric IQ toolbox.

Fabric IQ is an MCP server. The tool is published once as a Foundry *toolbox*
(see `create_fabric_iq_toolbox.py` in the parent sample), and this agent attaches
the latest published version at startup.

Run locally:
    python src/fabric-iq-responses/main.py
    # serves the Responses protocol on http://localhost:8088

Deployed:
    azd ai agent init ... && azd deploy
"""

import logging
import os
import sys

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient, FoundryToolbox
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.projects import AIProjectClient
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Fabric responses contain citation markers (e.g. U+3010) that the default
# Windows console encoding (cp1252) cannot encode, which would crash logging.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fabric-iq-responses")

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

# DefaultAzureCredential covers both cases: the developer's az login locally, and
# the agent's managed identity once hosted in Foundry. AzureCliCredential alone
# would fail in the container, which has no az CLI.
_credential = DefaultAzureCredential()


def _latest_toolbox_version() -> str:
    """Return the highest published version of the configured toolbox.

    Resolved once at startup so every request uses the same toolbox, and so a
    missing toolbox fails the container immediately with a clear message rather
    than surfacing as an opaque 404 on the first user question.
    """
    if not PROJECT_ENDPOINT:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT is required. Example: "
            "https://<resource>.ai.azure.com/api/projects/<project_name>"
        )

    with AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=_credential) as project:
        try:
            versions = [str(v.version) for v in project.toolboxes.list_versions(TOOLBOX_NAME)]
        except ResourceNotFoundError:
            raise ValueError(
                f"Toolbox '{TOOLBOX_NAME}' does not exist in this project. "
                "Publish it first with create_fabric_iq_toolbox.py."
            ) from None

    if not versions:
        raise ValueError(f"Toolbox '{TOOLBOX_NAME}' has no published versions.")

    # The service happens to list versions newest-first, but compare numerically
    # rather than trusting that ordering.
    numeric = [v for v in versions if v.isdigit()]
    return max(numeric, key=int) if numeric else versions[0]


def build_agent() -> Agent:
    version = _latest_toolbox_version()
    toolbox_url = (
        f"{PROJECT_ENDPOINT}/toolboxes/{TOOLBOX_NAME}/mcp?api-version=v1"
    )
    logger.info("Using toolbox %s version %s", TOOLBOX_NAME, version)
    logger.info("Toolbox MCP endpoint: %s", toolbox_url)

    # The toolbox is passed unconnected on purpose. Agent connects its MCP tools
    # on the first run, inside the server's own event loop, and keeps them
    # connected for the process lifetime. Connecting here instead would bind the
    # MCP session to a throwaway loop that the server never uses.
    #
    # FoundryToolbox already forwards the platform's per-request caller-context
    # headers on every MCP call, so the Fabric IQ connection's on-behalf-of
    # authentication keeps working when hosted.
    toolbox = FoundryToolbox(_credential, url=toolbox_url)

    # FoundryChatClient resolves the model at construction time, so it must be
    # passed here (or via FOUNDRY_MODEL); setting it only on Agent raises
    # "Model is required."
    # project_endpoint must be passed explicitly: the client only reads the
    # FOUNDRY_PROJECT_ENDPOINT env var, not AZURE_AI_PROJECT_ENDPOINT.
    chat_client = FoundryChatClient(
        project_endpoint=PROJECT_ENDPOINT,
        model=MODEL_DEPLOYMENT_NAME,
        credential=_credential,
    )

    return Agent(
        name="fabric-iq-responses",
        client=chat_client,
        instructions=INSTRUCTIONS,
        tools=[toolbox],
    )


def main() -> None:
    # PORT is injected by the Foundry hosting runtime; 8088 matches `azd ai agent run`.
    port = int(os.environ.get("PORT", "8088"))
    ResponsesHostServer(build_agent()).run(port=port)


if __name__ == "__main__":
    main()
