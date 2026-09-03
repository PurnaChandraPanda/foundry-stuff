"""Foundry hosted agent that answers questions using a Microsoft Fabric data agent.

Speaks the **invocations** protocol (not Responses): the hosting runtime posts to
/invoke and this module owns the request/response shape, so conversation history
is kept here in AgentSession rather than by the platform.

Run locally:
    python src/fabric-dataagent-invocations/main.py
    # serves the invocations protocol on http://localhost:8088

    # The route is /invocations (not /invoke) -- verified from app.routes.
    # Session id comes from the agent_session_id query param, else a fresh UUID.
    curl -X POST "http://localhost:8088/invocations?agent_session_id=demo" \
      -H "Content-Type: application/json" \
      -d '{"message": "which month had highest travel rides and which month had lowest"}'

    # streaming (SSE)
    curl -N -X POST "http://localhost:8088/invocations?agent_session_id=demo" \
      -H "Content-Type: application/json" \
      -d '{"message": "and what was the total?", "stream": true}'

Deployed:
    azd ai agent init ... && azd deploy
"""

import json
import logging
import os
import sys
from collections.abc import AsyncGenerator

from agent_framework import Agent, AgentSession
from agent_framework.foundry import FoundryChatClient
from azure.ai.agentserver.invocations import InvocationAgentServerHost
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse

# Fabric responses contain citation markers (e.g. U+3010) that the default
# Windows console encoding (cp1252) cannot encode, which would crash logging.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fabric-dataagent-invocations")

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
    connection_id = _resolve_connection_id()
    logger.info("Using Fabric connection: %s", connection_id)

    # Pass the tool as a plain dict. agent_framework_foundry sanitizes hosted
    # tools with a shallow dict(), which leaves the nested
    # FabricDataAgentToolParameters as an Azure model object and fails with
    # "Object of type FabricDataAgentToolParameters is not JSON serializable".
    # as_dict() serializes the whole tree.
    fabric_tool = FoundryChatClient.get_fabric_tool(connection_id=connection_id).as_dict()
    logger.debug("Fabric tool payload: %s", json.dumps(fabric_tool))

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
        name="fabric-dataagent-invocations",
        client=chat_client,
        instructions=INSTRUCTIONS,
        tools=[fabric_tool],
        # This module owns conversation history via AgentSession, so the service
        # does not need to store it. Matches the public invocations sample.
        default_options={"store": False},
    )


# Built at import time: the hosting runtime imports this module to find `app`,
# it does not execute main(). Anything created only inside main() would be dead
# code in the deployed container.
agent = build_agent()

app = InvocationAgentServerHost()

# In-memory session store, keyed by the session id the runtime assigns.
# WARNING: lost on restart and not shared across replicas. Use durable storage
# for anything beyond a sample.
_sessions: dict[str, AgentSession] = {}


@app.invoke_handler
async def handle_invoke(request: Request) -> Response:
    """Answer one invocation, streaming over SSE when the caller asks for it.

    POST /invocations
        {"message": "<question>", "stream": false}

    The invocations protocol leaves the wire shape to the handler, unlike
    Responses where the platform defines it. Session id comes from
    request.state, set by the runtime from the ``agent_session_id`` query
    parameter, the FOUNDRY_AGENT_SESSION_ID env var, or a fresh UUID
    (azure/ai/agentserver/invocations/_invocation.py, _create_invocation_endpoint).
    """
    session_id = request.state.session_id
    logger.info(
        "invocation %s session=%s user=%s",
        getattr(request.state, "invocation_id", None),
        session_id,
        getattr(request.state, "user_id", None) or "-",
    )

    data = await request.json()

    stream = data.get("stream", False)
    user_message = data.get("message")
    if user_message is None:
        error = "Missing 'message' in request"
        if stream:
            return StreamingResponse(content=error, status_code=400)
        return Response(content=error, status_code=400)

    session = _sessions.setdefault(session_id, AgentSession(session_id=session_id))

    if stream:

        async def stream_response() -> AsyncGenerator[str]:
            async for update in agent.run(user_message, session=session, stream=True):
                if update.text:
                    yield update.text

        return StreamingResponse(
            stream_response(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )

    response = await agent.run(user_message, session=session)
    return JSONResponse({"response": response.text})


def main() -> None:
    # PORT is injected by the Foundry hosting runtime; 8088 matches `azd ai agent run`.
    port = int(os.environ.get("PORT", "8088"))
    app.run(port=port)


if __name__ == "__main__":
    main()
