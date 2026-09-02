"""Diagnose the Foundry -> Fabric IQ wiring.

Fabric IQ is reached over MCP, so a failure is almost always one of three things:
the project connection is missing or misshaped, the MCP endpoint URL is wrong or
the item is unpublished, or the signed-in user cannot reach the Fabric item.

This script checks each in turn, using the same identity your agent will run
under. Every check prints what it observed rather than only pass/fail, so the
output is usable in a support thread.

Environment variables:
    AZURE_AI_PROJECT_ENDPOINT   required
    FABRIC_IQ_CONNECTION_NAME   required
    FABRIC_IQ_ITEM_TYPE         dataagent | ontology | semanticmodel
    FABRIC_WORKSPACE_ID         GUID from the Fabric portal URL
    FABRIC_ARTIFACT_ID          GUID of the Fabric item
    FABRIC_IQ_SERVER_URL        optional override; wins over the derived URL
"""

import json
import os
import sys
import urllib.error
import urllib.request

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from fabric_iq_config import resolve_item_type, resolve_server_url

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

load_dotenv()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
CONNECTION_NAME = os.environ.get("FABRIC_IQ_CONNECTION_NAME")

FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"


def _mcp_call(url: str, token: str, payload: dict) -> dict:
    """Send one JSON-RPC message to an MCP endpoint and return the parsed reply."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            # Streamable-HTTP MCP servers may reply with either content type.
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read().decode(errors="replace")
    except urllib.error.HTTPError as error:
        return {"_status": error.code, "_body": error.read().decode(errors="replace")}
    except urllib.error.URLError as error:
        return {"_status": 0, "_body": str(error)}

    # An SSE reply wraps the JSON payload in "data:" lines.
    if body.lstrip().startswith("event:") or body.lstrip().startswith("data:"):
        for line in body.splitlines():
            if line.startswith("data:"):
                body = line[len("data:") :].strip()
                break
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"_status": "unparsed", "_body": body[:500]}


def check_connection() -> str | None:
    """Confirm the project connection exists and is shaped for Fabric IQ."""
    print("== 1. Foundry project connection ==")
    if not PROJECT_ENDPOINT or not CONNECTION_NAME:
        print("  FAIL: AZURE_AI_PROJECT_ENDPOINT and FABRIC_IQ_CONNECTION_NAME are required.")
        return None

    try:
        with (
            DefaultAzureCredential() as credential,
            AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential) as project,
        ):
            connection = project.connections.get(CONNECTION_NAME)
    except Exception as exc:  # noqa: BLE001 - report whatever the SDK raised
        print(f"  FAIL: cannot read connection '{CONNECTION_NAME}': {type(exc).__name__}: {exc}")
        print("  Fix: run ./create_fabric_iq_connection.sh")
        return None

    print(f"  OK: {connection.id}")
    print(f"  type={getattr(connection, 'type', None)} target={getattr(connection, 'target', None)}")
    return connection.id


def resolve_url_or_report() -> str | None:
    """Derive the MCP URL, turning a config mistake into a readable message."""
    try:
        return resolve_server_url()
    except ValueError as exc:
        print("\n== 2. Fabric IQ MCP endpoint ==")
        print(f"  FAIL: {exc}")
        return None


def check_mcp_endpoint(url: str) -> bool:
    """Reach the Fabric MCP endpoint as the signed-in user and list its tools.

    A 404 means the URL is wrong or the item is not published. A 401 means the
    user cannot reach the item. Both are Fabric-side problems, not agent bugs.
    """
    print("\n== 2. Fabric IQ MCP endpoint ==")
    print(f"  item type: {resolve_item_type()}")
    print(f"  url: {url}")

    with DefaultAzureCredential() as credential:
        token = credential.get_token(FABRIC_SCOPE).token

    handshake = _mcp_call(
        url,
        token,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "diagnose-fabric-iq", "version": "1.0"},
            },
        },
    )

    if "_status" in handshake:
        status = handshake["_status"]
        print(f"  FAIL: HTTP {status}")
        print(f"  {handshake.get('_body', '')[:400]}")
        if status == 404:
            print(
                "  Fix: the server_url is wrong or the Fabric item is not published.\n"
                "       Verify the workspace and item GUIDs in the Fabric portal URL."
            )
        elif status in (401, 403):
            print(
                "  Fix: the signed-in user cannot reach this Fabric item. Grant that\n"
                "       user read access to the item and each underlying data source."
            )
        return False

    server = handshake.get("result", {}).get("serverInfo", {})
    print(f"  OK: connected to {server.get('name')} v{server.get('version')}")

    tools = _mcp_call(url, token, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    listed = tools.get("result", {}).get("tools", [])
    if not listed:
        print("  WARN: the endpoint exposes no tools; check that the item is published.")
        return False

    print(f"  Tools exposed ({len(listed)}):")
    for tool in listed:
        print(f"    - {tool.get('name')}: {tool.get('description')}")
    return True


def main() -> int:
    connection_id = check_connection()

    url = resolve_url_or_report()
    if not url:
        return 1

    reachable = check_mcp_endpoint(url)

    print("\n== Summary ==")
    print(f"  connection : {'OK' if connection_id else 'FAIL'}")
    print(f"  mcp endpoint: {'OK' if reachable else 'FAIL'}")
    if connection_id and reachable:
        print("\nBoth sides look good. Run create_fabric_iq_prompt_agent.py next.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
