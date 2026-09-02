"""Diagnose the Foundry -> Microsoft Fabric data agent wiring.

Targets the runtime failure:
    Create run failed: ... "Stage configuration not found."

The Fabric tool uses identity passthrough (On-Behalf-Of), so the *signed-in
user* must be able to read the published Fabric data agent. This script checks
both sides: the Foundry project connection, and the Fabric artifact/workspace
permissions for the current user.

Optional environment variables for the Fabric-side checks:
    FABRIC_WORKSPACE_ID   GUID from .../groups/<workspace_id>/aiskills/...
    FABRIC_ARTIFACT_ID    GUID from .../aiskills/<artifact_id>...
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
FABRIC_CONNECTION_NAME = os.environ.get("FABRIC_CONNECTION_NAME")
FABRIC_WORKSPACE_ID = os.environ.get("FABRIC_WORKSPACE_ID")
FABRIC_ARTIFACT_ID = os.environ.get("FABRIC_ARTIFACT_ID")

FABRIC_API = "https://api.fabric.microsoft.com/v1"
FABRIC_SCOPE = "https://api.fabric.microsoft.com/.default"


def _fabric_post_lro(path: str, token: str, timeout_s: int = 90):
    """POST a long-running Fabric operation and return its final result body."""
    request = urllib.request.Request(
        f"{FABRIC_API}/{path}",
        data=b"",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            operation_url = response.headers.get("Location")
            if response.status == 200:
                return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return {"_error": error.code, "_body": error.read().decode(errors="replace")}
    except urllib.error.URLError as error:
        return {"_error": 0, "_body": str(error)}

    if not operation_url:
        return {"_error": "no-location"}

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(3)
        status_request = urllib.request.Request(
            operation_url, headers={"Authorization": f"Bearer {token}"}
        )
        try:
            with urllib.request.urlopen(status_request, timeout=60) as response:
                state = json.loads(response.read() or b"{}")
        except (urllib.error.HTTPError, urllib.error.URLError) as error:
            return {"_error": str(error)}

        if state.get("status") == "Succeeded":
            result_request = urllib.request.Request(
                f"{operation_url}/result", headers={"Authorization": f"Bearer {token}"}
            )
            with urllib.request.urlopen(result_request, timeout=60) as response:
                return json.loads(response.read() or b"{}")
        if state.get("status") == "Failed":
            return {"_error": "operation-failed", "_body": state}

    return {"_error": "timeout"}


def check_publish_state(token: str) -> bool:
    """Check whether the data agent has a published stage, not just a draft.

    The Foundry Fabric tool calls the *published* stage. If the item definition
    only contains Files/Config/draft/..., the agent was never published and the
    service reports "Stage configuration not found."
    """
    print()
    print("=" * 72)
    print("3. Fabric data agent publish state")
    print("=" * 72)

    if not FABRIC_WORKSPACE_ID or not FABRIC_ARTIFACT_ID:
        print("SKIP: set FABRIC_WORKSPACE_ID and FABRIC_ARTIFACT_ID to run this check.")
        return True

    definition = _fabric_post_lro(
        f"workspaces/{FABRIC_WORKSPACE_ID}/items/{FABRIC_ARTIFACT_ID}/getDefinition", token
    )
    if "_error" in definition:
        print(f"WARN: could not read the item definition: {definition}")
        return True

    paths = [part.get("path", "") for part in definition.get("definition", {}).get("parts", [])]
    print("\nDefinition parts:")
    for path in paths:
        print(f"  - {path}")

    has_draft = any("/draft/" in p for p in paths)
    has_published = any("/published/" in p for p in paths)

    print(f"\n  draft stage present:     {has_draft}")
    print(f"  published stage present: {has_published}")

    if has_published:
        print("\nOK: a published stage exists.")
        return True

    print("\nFAIL: the data agent has NO published stage (draft only).")
    print("      This is exactly what causes: \"Stage configuration not found.\"")
    print("      Open the data agent in Fabric and select Publish.")
    return False


def _fabric_get(path: str, token: str):
    """Return (status_code, parsed_body_or_text) for a Fabric REST GET."""
    request = urllib.request.Request(
        f"{FABRIC_API}/{path}",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            return error.code, json.loads(raw or b"{}")
        except json.JSONDecodeError:
            return error.code, raw.decode(errors="replace")
    except urllib.error.URLError as error:
        return 0, str(error)


def check_foundry_connection(credential) -> None:
    print("=" * 72)
    print("1. Foundry project connection")
    print("=" * 72)

    project = AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=credential)
    print(f"Project endpoint: {PROJECT_ENDPOINT}")

    connections = list(project.connections.list())
    print("\nConnections in this project:")
    for conn in connections:
        print(f"  - {conn.name}  (type={conn.type})")
    

    if not FABRIC_CONNECTION_NAME:
        print("\nWARN: FABRIC_CONNECTION_NAME is not set.")
        return

    names = [c.name for c in connections]
    if FABRIC_CONNECTION_NAME not in names:
        print(f"\nFAIL: no connection named '{FABRIC_CONNECTION_NAME}' in this project.")
        print("      Create a Microsoft Fabric connection under")
        print("      Project -> Manage -> Project details -> Connected resources.")
        return

    connection = project.connections.get(FABRIC_CONNECTION_NAME)
    print(f"\nResolved '{FABRIC_CONNECTION_NAME}':")
    print(f"  id:       {connection.id}")
    print(f"  type:     {connection.type}")
    print(f"  metadata: {dict(connection.metadata) if connection.metadata else '{}'}")


def check_fabric_access(credential) -> bool:
    """Verify the signed-in user can actually reach the Fabric data agent."""
    print()
    print("=" * 72)
    print("2. Fabric access for the signed-in user (identity passthrough)")
    print("=" * 72)

    if not FABRIC_WORKSPACE_ID or not FABRIC_ARTIFACT_ID:
        print("SKIP: set FABRIC_WORKSPACE_ID and FABRIC_ARTIFACT_ID to run these checks.")
        print("      Copy both GUIDs from the data agent URL:")
        print("      .../groups/<workspace_id>/aiskills/<artifact_id>...")
        return True

    token = credential.get_token(FABRIC_SCOPE).token
    healthy = True

    status, body = _fabric_get("workspaces", token)
    if status == 200:
        workspaces = body.get("value", [])
        print(f"\nWorkspaces visible to you ({len(workspaces)}):")
        for workspace in workspaces:
            marker = "  <-- target" if workspace.get("id") == FABRIC_WORKSPACE_ID else ""
            print(f"  - {workspace.get('displayName')}  {workspace.get('id')}{marker}")
        if not any(w.get("id") == FABRIC_WORKSPACE_ID for w in workspaces):
            print(f"\nFAIL: workspace {FABRIC_WORKSPACE_ID} is NOT in your visible workspaces.")
            print("      The Fabric tool runs as YOU (On-Behalf-Of), so it cannot read the")
            print("      data agent's published configuration.")
            healthy = False
    else:
        print(f"\nWARN: could not list workspaces (HTTP {status}): {body}")

    status, body = _fabric_get(f"workspaces/{FABRIC_WORKSPACE_ID}", token)
    print(f"\nGET workspace {FABRIC_WORKSPACE_ID} -> HTTP {status}")
    if status in (401, 403):
        print("FAIL: insufficient privileges on the workspace hosting the data agent.")
        print("      Ask a workspace admin to add you (Viewer or higher), and grant")
        print("      at least READ on the data agent and its data sources.")
        healthy = False
    elif status == 200:
        print(f"  OK: {body.get('displayName')}")

    status, body = _fabric_get(
        f"workspaces/{FABRIC_WORKSPACE_ID}/items/{FABRIC_ARTIFACT_ID}", token
    )
    print(f"\nGET item {FABRIC_ARTIFACT_ID} -> HTTP {status}")
    if status == 200:
        print(f"  displayName: {body.get('displayName')}")
        print(f"  type:        {body.get('type')}")
        if body.get("type") != "DataAgent":
            print(f"FAIL: expected type 'DataAgent', got '{body.get('type')}'.")
            healthy = False
    elif status == 404:
        print("FAIL: artifact not found in that workspace. The workspace_id/artifact_id")
        print("      pair in the Fabric connection is wrong. Recreate the connection.")
        healthy = False
    else:
        print(f"  {body}")
        healthy = False

    return healthy


def main() -> int:
    if not PROJECT_ENDPOINT:
        print("FAIL: AZURE_AI_PROJECT_ENDPOINT is not set.")
        print("      Expected: https://<resource>.ai.azure.com/api/projects/<project_name>")
        return 1

    credential = DefaultAzureCredential()

    check_foundry_connection(credential)
    healthy = check_fabric_access(credential)

    token = credential.get_token(FABRIC_SCOPE).token
    published = check_publish_state(token)

    print()
    print("=" * 72)
    print("Summary")
    print("=" * 72)
    if healthy and published:
        print("All checks passed. If the run still fails, the data agent may have been")
        print("changed after publishing - republish it and try again.")
    elif not healthy:
        print("Fix the access problems above first: the Fabric tool runs as the")
        print("signed-in user (On-Behalf-Of), so that user needs workspace and")
        print("data source access.")
    else:
        print("Publish the Fabric data agent, then re-run run_fabric_prompt_agent.py.")

    return 0 if (healthy and published) else 1


if __name__ == "__main__":
    sys.exit(main())
