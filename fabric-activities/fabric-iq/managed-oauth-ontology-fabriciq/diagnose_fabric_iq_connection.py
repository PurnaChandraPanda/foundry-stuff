"""Discover Fabric tools through a Foundry toolbox or directly, without an LLM.

The default toolbox probe also verifies the UserEntraToken connection.
Direct mode bypasses Foundry. --entity-name also executes a metadata tool.
Neither discovery nor entity metadata proves access to backing-table rows.
"""

import argparse
import asyncio
import json
import sys
import urllib.error
from typing import Literal

from azure.ai.projects import AIProjectClient
from azure.core.exceptions import AzureError
from azure.identity import AzureCliCredential
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.shared.exceptions import McpError

from fabric_iq_config import resolve_server_url, toolbox_mcp_url
from fabric_iq_oauth import (
    CONSENT_GUIDANCE,
    load_environment,
    report_oauth_error,
    required_env,
    verify_user_entra_connection,
)

load_environment()


def show_setup() -> None:
    print(
        "Create a Fabric IQ UserEntraToken connection matching portal reference daontology1.\n"
        "Create/update: ./create_fabric_iq_connection.sh (includes az login)\n"
        "Auth: UserEntraToken; audience: https://api.fabric.microsoft.com\n"
        "Metadata: type=fabric_iq_preview. No connector name or client secret is needed.\n"
        "Alternatively, set the name of an existing compatible connection in .env.\n"
        f"Connection name: {required_env('FABRIC_IQ_CONNECTION_NAME')}\n"
        f"Ontology endpoint: {resolve_server_url()}\n"
        "Set TENANT_ID in .env. If skipping creation, use az login --tenant <that-tenant-id>.\n"
        "Creation uses tenant-scoped ARM REST; azd is not required.\n"
        "Sign in as a user with Foundry and Fabric access; complete consent if requested.\n"
        "Then run: python diagnose_fabric_iq_connection.py --connection-only\n"
        "This command prints instructions only; no Azure resources were created."
    )


async def probe_toolbox(
    credential: AzureCliCredential, connection_id: str, version: str, entity_name: str | None
) -> None:
    endpoint = required_env("AZURE_AI_PROJECT_ENDPOINT")
    toolbox_name = required_env("FABRIC_IQ_TOOLBOX_NAME")
    with AIProjectClient(endpoint=endpoint, credential=credential) as project:
        definition = project.toolboxes.get_version(name=toolbox_name, version=version)
    if not any(
        tool.get("type") == "fabric_iq_preview"
        and tool.get("project_connection_id") == connection_id
        for tool in definition.as_dict().get("tools", [])
    ):
        raise ValueError(
            "This toolbox version does not reference the configured UserEntraToken connection. "
            "Publish it with create_fabric_iq_toolbox.py and select the printed version."
        )

    url = toolbox_mcp_url(endpoint, toolbox_name, version)
    await probe_mcp(credential, url, "toolbox", entity_name)


async def probe_mcp(
    credential: AzureCliCredential,
    url: str,
    source: Literal["toolbox", "direct"],
    entity_name: str | None,
) -> None:
    label = "Foundry toolbox" if source == "toolbox" else "Direct Fabric"
    scope = (
        "https://ai.azure.com/.default"
        if source == "toolbox"
        else "https://api.fabric.microsoft.com/.default"
    )
    print(f"{label} MCP endpoint: {url}")
    token = credential.get_token(scope).token
    async with streamablehttp_client(
        url, headers={"Authorization": f"Bearer {token}"}
    ) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            page = await session.list_tools()
            tools = list(page.tools)
            while page.nextCursor:
                page = await session.list_tools(cursor=page.nextCursor)
                tools.extend(page.tools)
            if not tools:
                raise ValueError(f"{label} returned no tools.")
            print(f"{label} tool names ({len(tools)}):")
            for tool in tools:
                print(f"  {tool.name}: {tool.description}")
            if source == "direct":
                print("For local_fabriciq_direct_agent.py, use these raw names:")
                print(f"ALLOWED_TOOLS='{json.dumps([tool.name for tool in tools])}'")
            else:
                print(
                    "These names are for the Foundry toolbox, not the direct client's ALLOWED_TOOLS. "
                    "Use --tool-source direct to discover raw Fabric names."
                )
            if entity_name is not None:
                tool = next(
                    (
                        tool for tool in tools
                        if (
                            tool.name.split("___")[-1] if source == "toolbox" else tool.name
                        ) == "list_ontology_entities"
                    ),
                    None,
                )
                if tool is None:
                    raise ValueError(f"{label} exposes no list_ontology_entities tool.")
                result = await session.call_tool(tool.name, {"entityName": entity_name})
                print(result.model_dump_json(indent=2))
                if result.isError:
                    raise ValueError("The metadata tool returned isError=true; see the result above.")
                print("Metadata tool execution succeeded; backing-table queries remain untested.")
            else:
                print("Tool discovery succeeded; tool execution and backing-table queries remain untested.")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--setup", action="store_true", help="Print portal setup instructions only.")
    mode.add_argument("--connection-only", action="store_true", help="Only verify ARM connection metadata.")
    parser.add_argument(
        "--tool-source", choices=("toolbox", "direct"), default="toolbox",
        help="Discover toolbox-prefixed names or raw direct Fabric names (default: toolbox).",
    )
    parser.add_argument("--toolbox-version", help="Published toolbox version to inspect (default: 1).")
    parser.add_argument("--entity-name", help="Also call the entity metadata tool using an exact name.")
    args = parser.parse_args()
    if args.tool_source == "direct" and (
        args.setup or args.connection_only or args.toolbox_version is not None
    ):
        parser.error(
            "--tool-source direct cannot be combined with --setup, "
            "--connection-only, or --toolbox-version."
        )
    try:
        if args.setup:
            show_setup()
            return 0
        with AzureCliCredential(tenant_id=required_env("TENANT_ID")) as credential:
            if args.tool_source == "direct":
                print(
                    "Direct Fabric call as the Azure CLI user; bypasses Foundry connection/toolbox "
                    "checks and ignores ALLOWED_TOOLS for discovery."
                )
                await probe_mcp(credential, resolve_server_url(), "direct", args.entity_name)
            else:
                connection_id = verify_user_entra_connection(credential)
                if not args.connection_only:
                    await probe_toolbox(
                        credential, connection_id, args.toolbox_version or "1", args.entity_name
                    )
        return 0
    except (AzureError, urllib.error.URLError, ValueError) as error:
        report_oauth_error(error)
        return 1


if __name__ == "__main__":
    exit_code = 1
    try:
        exit_code = asyncio.run(main())
    except* McpError as errors:
        report_oauth_error(errors)
        print(CONSENT_GUIDANCE, file=sys.stderr)
    sys.exit(exit_code)
