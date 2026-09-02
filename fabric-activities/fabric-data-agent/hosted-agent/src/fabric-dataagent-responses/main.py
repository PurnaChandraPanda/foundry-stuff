"""Foundry hosted agent that answers questions using a Microsoft Fabric data agent.

Run locally:
    python src/fabric-dataagent-responses/main.py
    # serves the Responses protocol on http://localhost:8088

Deployed:
    azd ai agent init ... && azd deploy
"""

import base64
import json
import logging
import os
import sys

from agent_framework import Agent, AgentContext, agent_middleware
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.ai.agentserver.core import get_request_context
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

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

INSTRUCTIONS = (
    "You are a helpful assistant. Use the connected Microsoft Fabric data agent "
    "to answer questions about enterprise data. Always ground your answer in the "
    "data the tool returns and state the numbers you used."
)

# DefaultAzureCredential covers both cases: the developer's az login locally, and
# the agent's managed identity once hosted in Foundry. AzureCliCredential alone
# would fail in the container, which has no az CLI.
_credential = DefaultAzureCredential()

# Scope the SDK itself requests (azure/ai/projects/_configuration.py).
_FOUNDRY_SCOPE = "https://ai.azure.com/.default"


def _log_container_identity() -> None:
    """Log which identity this container presents to Foundry.

    The Fabric tool is a *declaration* only: get_fabric_tool() returns a
    MicrosoftFabricPreviewTool payload with no callable. The container never
    calls Fabric -- Foundry resolves the connection and makes that call
    server-side, so the Fabric-facing token cannot be observed from here.

    What is observable is the token this container sends to Foundry, which is
    the input to whatever Foundry does downstream. The 'idtyp' claim is the
    discriminator: 'user' when running locally under az login, 'app' when
    running as the hosted managed identity. If Fabric OBO rejects service
    principals, idtyp=app in the deployed log is the confirmation.

    Claims only are logged; the raw token is never written out.
    """
    try:
        token = _credential.get_token(_FOUNDRY_SCOPE).token
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        logger.info(
            "Container identity -> idtyp=%s oid=%s appid=%s tid=%s",
            claims.get("idtyp"),
            claims.get("oid"),
            claims.get("appid"),
            claims.get("tid"),
        )
    except Exception:  # diagnostics must never take the server down
        logger.exception("Could not read container identity")


@agent_middleware
async def _log_caller_identity(context: AgentContext, call_next) -> None:
    """Log the caller identity Foundry forwards with each request.

    This has to run inside the agent invocation, not as Starlette middleware:
    the platform context is set deep inside the endpoint handler
    (azure/ai/agentserver/responses/hosting/_endpoint_handler.py), so anything
    added via app.add_middleware() runs *before* it exists and would log all
    None values.

    user_id populated but Fabric still failing => the caller identity reaches
    this agent and is lost further downstream. user_id None => there is no
    caller identity for Foundry to impersonate with in the first place.
    """
    try:
        ctx = get_request_context()
        logger.info(
            "Caller -> user_id=%s session_id=%s call_id=%s headers=%s",
            ctx.user_id,
            ctx.session_id,
            ctx.call_id,
            sorted(ctx.platform_headers() or {}),
        )
    except Exception:
        logger.exception("Could not read caller identity")

    await call_next()


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

def build_agent() -> Agent:
    _log_container_identity()

    connection_id = _resolve_connection_id()
    logger.info("Using Fabric connection: %s", connection_id)


    # Pass the tool as a plain dict. agent_framework_foundry sanitizes hosted
    # tools with a shallow dict(), which leaves the nested
    # FabricDataAgentToolParameters as an Azure model object and fails with
    # "Object of type FabricDataAgentToolParameters is not JSON serializable".
    # as_dict() serializes the whole tree.
    fabric_tool = FoundryChatClient.get_fabric_tool(connection_id=connection_id).as_dict()

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
        middleware=[_log_caller_identity],
    )


def main() -> None:
    # PORT is injected by the Foundry hosting runtime; 8088 matches `azd ai agent run`.
    port = int(os.environ.get("PORT", "8088"))
    ResponsesHostServer(build_agent()).run(port=port)


if __name__ == "__main__":
    main()
