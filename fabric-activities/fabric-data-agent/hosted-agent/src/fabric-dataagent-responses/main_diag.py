"""Diagnostics variant of main.py - showcases how to use _diagnostics.py.

Identical to main.py except that it wires in every hook the diagnostics module
offers. Use it when a deployed container misbehaves and the ordinary logs are
not enough.

Run locally:
    python src/fabric-dataagent-responses/main_diag.py
    # serves the Responses protocol on http://localhost:8088

Deploy this instead of main.py by pointing the manifest at it:
    # azure.yaml
    entryPoint: main_diag.py
then redeploy and watch `azd ai agent monitor --follow` for AGENTDIAG lines.

The hooks used below, and where each must go:

    build_agent()   configure() / set_context() / start()
                    start() must be here rather than in main(): under
                    `dependencyResolution: remote_build` the runtime imports
                    this module and supplies its own launcher, so main() never
                    executes in the container.

    Agent(...)      middleware=diagnostics.agent_middlewares()
                    per-run caller identity - the identity the Fabric tool's
                    On-Behalf-Of exchange is attempted for.

    main()          install_asgi(server)
                    every HTTP request beneath the protocol layer, including
                    the ones that never reach the agent (404s, health probes).

Everything runs through _diagnostics.py, which itself defaults to OFF. This file
opts in, so probes are **on by default here**; set AGENT_DIAG_PROBE=0 to silence
them and behave exactly like main.py.

Each probe cycle emits token claims, listSecrets at project and account scope,
and a 443 reachability test (DNS/TCP/TLS) against AAD, ARM, this project's
Foundry endpoint and Fabric. Override those hosts with AGENT_DIAG_EGRESS.
"""

import json
import logging
import os
import sys

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from _diagnostics import diagnostics

# Fabric responses contain citation markers (e.g. U+3010) that the default
# Windows console encoding (cp1252) cannot encode, which would crash logging.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fabric-dataagent-responses")

load_dotenv()

PROJECT_ENDPOINT = os.environ.get("AZURE_AI_PROJECT_ENDPOINT")
PROJECT_ID = os.environ.get("AZURE_AI_PROJECT_ID")
MODEL_DEPLOYMENT_NAME = os.environ.get("AZURE_AI_MODEL_DEPLOYMENT_NAME")
FABRIC_CONNECTION_NAME = os.environ.get("FABRIC_CONNECTION_NAME")

# This is the diagnostics copy, so probes default to ON here. The module itself
# defaults to OFF, which is why the hooks below are safe to leave in main.py.
PROBE_ENABLED = os.environ.get("AGENT_DIAG_PROBE", "1") != "0"

INSTRUCTIONS = (
    "You are a helpful assistant. Use the connected Microsoft Fabric data agent "
    "to answer questions about enterprise data. Always ground your answer in the "
    "data the tool returns and state the numbers you used."
)

# DefaultAzureCredential covers both cases: the developer's az login locally, and
# the agent's managed identity once hosted in Foundry. AzureCliCredential alone
# would fail in the container, which has no az CLI.
_credential = DefaultAzureCredential()


def _resolve_connection_id() -> str:
    """Return the ARM id of the Fabric connection, built from the connection name.

    The Fabric tool needs the connection's **ARM resource id**:

        /subscriptions/<sub>/resourceGroups/<rg>/providers/
        Microsoft.CognitiveServices/accounts/<account>/projects/<project>/connections/<name>

    Building it from AZURE_AI_PROJECT_ID needs no API call, so the hosted
    identity does not need permission to list project connections. Building it
    from AZURE_AI_PROJECT_ENDPOINT instead would produce an https:// URL, which
    the service rejects with "No CustomKeys connection found for AzureFabric".

    Falls back to an SDK lookup when AZURE_AI_PROJECT_ID is not set.
    """
    if not FABRIC_CONNECTION_NAME:
        raise ValueError("FABRIC_CONNECTION_NAME is required.")

    if PROJECT_ID:
        return f"{PROJECT_ID}/connections/{FABRIC_CONNECTION_NAME}"

    if not PROJECT_ENDPOINT:
        raise ValueError(
            "Set AZURE_AI_PROJECT_ID or AZURE_AI_PROJECT_ENDPOINT so the Fabric "
            "connection id can be resolved."
        )

    with AIProjectClient(endpoint=PROJECT_ENDPOINT, credential=_credential) as project:
        return project.connections.get(FABRIC_CONNECTION_NAME).id


# Diagnostics now live in _diagnostics.py so they can be reused and
# extended without editing this file. Add extra background probes with:
#
#     @diagnostics.probe("my-check")
#     def _my_check() -> None:
#         resp = diagnostics.call_arm(f"{PROJECT_ID}/connections", method="GET")
#         diagnostics.emit(f"connections -> {resp.status_code}")
#
# Or override the hosts the built-in egress probe tests (it already covers
# AAD, ARM, this project's Foundry endpoint and Fabric):
#
#     diagnostics.check_egress("management.azure.com",
#                              "api.fabric.microsoft.com")


def build_agent() -> Agent:
    connection_id = _resolve_connection_id()
    logger.info("Using Fabric connection: %s", connection_id)

    # Pass the tool as a plain dict. agent_framework_foundry sanitizes hosted
    # tools with a shallow dict(), which leaves the nested
    # FabricDataAgentToolParameters as an Azure model object and fails with
    # "Object of type FabricDataAgentToolParameters is not JSON serializable".
    # as_dict() serializes the whole tree.
    fabric_tool = FoundryChatClient.get_fabric_tool(connection_id=connection_id).as_dict()

    # --- diagnostics hooks (no-ops unless AGENT_DIAG_PROBE is set) --------
    diagnostics.configure(credential=_credential, enabled=PROBE_ENABLED)
    # Echoed every cycle, so the exact payload Foundry receives lands in a
    # monitor capture taken long after startup.
    diagnostics.set_context(
        connection_id=connection_id,
        fabric_tool=json.dumps(fabric_tool),
    )
    # Started here, not in main(): with `dependencyResolution: remote_build`
    # the runtime imports this module and never calls main().
    diagnostics.start()
    # ----------------------------------------------------------------------

    # FoundryChatClient resolves the model at construction time, so it must
    # be passed here (or via FOUNDRY_MODEL); setting it only on Agent raises
    # "Model is required."
    # project_endpoint must be passed explicitly: the client only reads the
    # FOUNDRY_PROJECT_ENDPOINT env var, not AZURE_AI_PROJECT_ENDPOINT.
    chat_client = FoundryChatClient(
        project_endpoint=PROJECT_ENDPOINT,
        model=MODEL_DEPLOYMENT_NAME,
        credential=_credential,
        allow_preview=True,
    )

    return Agent(
        name="fabric-dataagent-responses",
        client=chat_client,
        instructions=INSTRUCTIONS,
        tools=[fabric_tool],
        middleware=diagnostics.agent_middlewares(),
    )


def main() -> None:
    # A boot marker. If this never appears after a redeploy, the container is
    # not running this file and no other diagnostic here can be trusted.
    diagnostics.emit(
        f"boot: probe_enabled={PROBE_ENABLED} connection={FABRIC_CONNECTION_NAME}"
    )

    # PORT is injected by the Foundry hosting runtime; 8088 matches `azd ai agent run`.
    port = int(os.environ.get("PORT", "8088"))

    server = ResponsesHostServer(build_agent())
    diagnostics.install_asgi(server)
    server.run(port=port)


if __name__ == "__main__":
    main()
