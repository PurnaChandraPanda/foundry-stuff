"""Publish an APIM toolbox for explicitly approved unattended, read-only tools."""

import argparse

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import MCPToolboxTool
from azure.identity import AzureCliCredential

from config import allowed_tools, https_url, load_environment, resource_name


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-unattended",
        action="store_true",
        help="Confirm every tool in APIM_ALLOWED_TOOLS is reviewed and safe without per-call approval.",
    )
    args = parser.parse_args()
    if not args.allow_unattended:
        parser.error(
            "This toolbox uses require_approval='never'. Review APIM_ALLOWED_TOOLS, "
            "then explicitly pass --allow-unattended. Do not include write/destructive tools."
        )
    load_environment()
    tool = MCPToolboxTool(
        server_label=resource_name("APIM_MCP_SERVER_LABEL"),
        server_url=https_url("APIM_MCP_URL"),
        project_connection_id=resource_name("APIM_MCP_CONNECTION_NAME"),
        allowed_tools=allowed_tools(),
        require_approval="never",
    )
    with (
        AzureCliCredential() as credential,
        AIProjectClient(
            endpoint=https_url("AZURE_AI_PROJECT_ENDPOINT"), credential=credential
        ) as project,
    ):
        toolbox = project.toolboxes.create_version(
            name=resource_name("APIM_TOOLBOX_NAME"),
            description="Reviewed public APIM MCP tools for unattended agent use.",
            tools=[tool],
        )
    print(f"Created toolbox: {toolbox.name}, version: {toolbox.version}")
    print(f"Set APIM_TOOLBOX_VERSION={toolbox.version}")
    print("The connection stores the APIM key; the hosted agent does not receive it.")


if __name__ == "__main__":
    main()
