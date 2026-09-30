"""Diagnose the Foundry -> Fabric IQ wiring.

Check the Foundry connection and directly probe MCP tool discovery using current user. 
These checks do not verify token forwarding through a Foundry agent or toolbox, or execution against the underlying data sources.
Report transport and JSON-RPC errors, including capacity and permission errors.

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
CREDENTIAL = DefaultAzureCredential()
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
        reply = json.loads(body)
    except json.JSONDecodeError:
        return {"_status": "unparsed", "_body": body[:500]}
    if not isinstance(reply, dict):
        return {"_status": "unparsed", "_body": body[:500]}
    return reply


def _mcp_result_or_report(reply: dict, method: str) -> dict | None:
    """Return a successful result, or report why this MCP stage failed."""
    if "_status" in reply:
        status = reply["_status"]
        if status == 0:
            print(f"  FAIL: {method}: transport error")
        elif status == "unparsed":
            print(f"  FAIL: {method}: invalid MCP response")
        else:
            print(f"  FAIL: {method}: HTTP {status}")
        print(f"  {reply.get('_body', '')[:400]}")
        if status == 404:
            print(
                "  Check: verify the MCP URL and that the Fabric item is published."
            )
        elif status in (401, 403):
            print(
                "  Check: token audience, the 'Service principals can use Fabric APIs'\n"
                "         tenant setting, and SP access to the workspace and data sources."
            )
        return None

    if "error" in reply:
        error = reply["error"]
        if isinstance(error, dict):
            print(
                f"  FAIL: {method}: JSON-RPC error {error.get('code')}: "
                f"{error.get('message')}"
            )
            if "data" in error:
                print(f"  data: {json.dumps(error['data'], ensure_ascii=True)}")
            if error.get("message") == "FTL64 SKU Not Supported":
                print(
                    "  Check: Fabric data agent MCP requires paid F2-or-higher or\n"
                    "         P1-or-higher capacity. Verify the workspace capacity SKU."
                )
        else:
            print(f"  FAIL: {method}: malformed JSON-RPC error: {error!r}")
        return None

    result = reply.get("result")
    if not isinstance(result, dict):
        print(f"  FAIL: {method}: MCP response has no valid result object.")
        return None
    return result


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
    """Reach Fabric MCP as the service principal and report tool discovery."""
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

    initialized = _mcp_result_or_report(handshake, "initialize")
    if initialized is None:
        return False

    server = initialized.get("serverInfo")
    if not isinstance(server, dict) or not all(
        isinstance(server.get(key), str) and server[key]
        for key in ("name", "version")
    ):
        print("  FAIL: initialize: MCP result has no valid serverInfo.")
        return False
    print(f"  OK: connected to {server['name']} v{server['version']}")

    tools = _mcp_call(url, token, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    tool_result = _mcp_result_or_report(tools, "tools/list")
    if tool_result is None:
        return False
    listed = tool_result.get("tools")
    if not isinstance(listed, list) or not all(
        isinstance(tool, dict) and isinstance(tool.get("name"), str) and tool["name"]
        for tool in listed
    ):
        print("  FAIL: tools/list: MCP result has no valid tools array.")
        return False
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
        print(
            "\nConnection lookup and direct MCP tool discovery passed.\n"
            "Foundry/toolbox token forwarding and data queries are not tested."
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
