"""Publish a Foundry toolbox holding the Fabric IQ tool.

A toolbox registers a tool once and exposes it at an MCP endpoint that any agent
can attach to. Publishing is separate from consuming because the two have very
different lifetimes: you publish when the tool definition changes, and run agents
against it many times in between.

Run `fabric_iq_local_agent.py` afterwards to query it.

Usage:
    python create_fabric_iq_toolbox.py
    python create_fabric_iq_toolbox.py --list
"""

import argparse
import os
import sys

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import FabricIQPreviewToolboxTool
from azure.core.exceptions import ResourceNotFoundError
from azure.identity import AzureCliCredential
from dotenv import load_dotenv

from fabric_iq_config import resolve_item_type, resolve_server_url, toolbox_mcp_url

load_dotenv()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
CONNECTION_NAME = os.environ.get("FABRIC_IQ_CONNECTION_NAME")
TOOLBOX_NAME = os.environ.get("FABRIC_IQ_TOOLBOX_NAME", "fabric-iq-toolbox")
SERVER_LABEL = os.environ.get("FABRIC_IQ_SERVER_LABEL")


def _project(credential: AzureCliCredential) -> AIProjectClient:
    if not PROJECT_ENDPOINT:
        raise ValueError(
            "AZURE_AI_PROJECT_ENDPOINT is required. Example: "
            "https://<resource>.ai.azure.com/api/projects/<project_name>"
        )
    return AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)


def create_toolbox_version(credential: AzureCliCredential) -> str:
    """Publish a new toolbox version and return it.

    Existing versions are left untouched, so re-running this is safe and anything
    pinned to an older version keeps working.
    """
    if not CONNECTION_NAME:
        raise ValueError("FABRIC_IQ_CONNECTION_NAME is required.")

    server_url = resolve_server_url()

    with _project(credential) as project:
        connection_id = project.connections.get(CONNECTION_NAME).id
        print(f"Using connection id: {connection_id}")
        print(f"Item type: {resolve_item_type()}")
        print(f"Server URL: {server_url}")

        tool = FabricIQPreviewToolboxTool(project_connection_id=connection_id)
        if SERVER_LABEL:
            tool.server_label = SERVER_LABEL
        tool.server_url = server_url

        toolbox = project.toolboxes.create_version(
            name=TOOLBOX_NAME,
            description="Toolbox with the Fabric IQ tool",
            tools=[tool],
        )

    version = str(toolbox.version)
    print(f"\nCreated toolbox: {toolbox.name} (version={version})")
    print(f"Toolbox MCP endpoint: {toolbox_mcp_url(PROJECT_ENDPOINT, TOOLBOX_NAME, version)}")
    print("\nNext:\n  python fabric_iq_local_agent.py")
    return version


def list_versions(credential: AzureCliCredential) -> int:
    with _project(credential) as project:
        try:
            versions = [str(v.version) for v in project.toolboxes.list_versions(TOOLBOX_NAME)]
        except ResourceNotFoundError:
            print(f"Toolbox '{TOOLBOX_NAME}' does not exist yet.", file=sys.stderr)
            print(f"Create it:  python {os.path.basename(__file__)}", file=sys.stderr)
            return 1

    if not versions:
        print(f"Toolbox '{TOOLBOX_NAME}' has no versions.", file=sys.stderr)
        return 1

    print(f"Toolbox '{TOOLBOX_NAME}' versions: {', '.join(versions)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish a Foundry toolbox holding the Fabric IQ tool."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List published versions instead of creating a new one.",
    )
    args = parser.parse_args()

    credential = AzureCliCredential()

    if args.list:
        return list_versions(credential)

    create_toolbox_version(credential)
    return 0


if __name__ == "__main__":
    sys.exit(main())
