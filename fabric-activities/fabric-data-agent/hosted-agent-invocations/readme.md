# Fabric data agent as a Foundry hosted agent (invocations protocol)

Deploys the Agent Framework agent from the parent folder as a **Foundry hosted
agent** speaking the **invocations** protocol.

- [`src/fabric-dataagent-invocations/main.py`](./src/fabric-dataagent-invocations/main.py) - the agent, served by `InvocationAgentServerHost`
- [`azure.yaml`](./azure.yaml) - azd project manifest
- [`.agentignore`](./.agentignore) - excludes `.env` and caches from the deploy ZIP

Run every command in this document **from this folder**, not the repo root.

## Invocations vs Responses

The sibling [`hosted-agent/`](../hosted-agent/readme.md) folder serves the same
agent over the Responses protocol. The differences that affect the code:

| | Responses | Invocations |
| --- | --- | --- |
| Host class | `ResponsesHostServer(agent)` | `InvocationAgentServerHost()` - takes **no** agent |
| Wiring | agent passed to the constructor | `@app.invoke_handler` on a request handler |
| Route | `POST /responses` | `POST /invocations` |
| Wire shape | defined by the platform | defined by **your handler** |
| History | managed by the platform | managed here, via `AgentSession` |
| Caller identity | `get_request_context()` from agent middleware | `request.state.user_id` / `.session_id` / `.call_id` |

Because the handler owns the wire shape, this sample accepts:

```json
{"message": "<question>", "stream": false}
```

and returns `{"response": "..."}`, or an SSE stream of text chunks when
`"stream": true`.

Session id is taken from `request.state.session_id`, which the runtime resolves
from the `agent_session_id` query parameter, the `FOUNDRY_AGENT_SESSION_ID` env
var, or a fresh UUID.

> The in-memory `_sessions` dict is lost on restart and is not shared across
> replicas. It is fine for a sample; use durable storage for anything real.

## Prerequisites

The Fabric connection must already exist in the Foundry project, and the Fabric
data agent must be **published**. See the [root readme](../readme.md) for how to
create the connection and how to diagnose it.

```bash
pip install -r src/fabric-dataagent-invocations/requirements.txt
```

`agent-framework-foundry-hosting` pulls in `azure-ai-agentserver-invocations`,
which provides `InvocationAgentServerHost`; no extra dependency is needed.

## How this differs from `fabric_local_agent.py`

Both build the same agent. Two changes matter once it runs in a container:

- **`DefaultAzureCredential`, not `AzureCliCredential`.** The hosted container
  has no `az` CLI; it authenticates with its managed identity.
  `DefaultAzureCredential` covers both that and your local `az login`.
- **The connection id is built without an API call** - it skips
  `project.connections.get(...)`, so the hosted identity does not need
  permission to list project connections. It must be the **ARM resource id**,
  derived from `AZURE_AI_PROJECT_ID`:

  ```
  /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>/connections/<name>
  ```

  Building it from `AZURE_AI_PROJECT_ENDPOINT` instead yields an `https://` URL,
  which the service rejects with
  `No CustomKeys connection found for AzureFabric`.

Three subtleties carried over from the local sample, all of which fail loudly if
dropped:

- `FoundryChatClient` resolves the model **at construction**, so `model=` must go
  on the client, not on `Agent`. Otherwise: `Model is required.`
- `FoundryChatClient` reads only the `FOUNDRY_PROJECT_ENDPOINT` env var, never
  `AZURE_AI_PROJECT_ENDPOINT`, so `project_endpoint=` is passed explicitly.
  Otherwise: `Either 'project_endpoint' or 'project_client' is required`.
- The Fabric tool is passed as `get_fabric_tool(...).as_dict()`. The hosting
  layer sanitizes tools with a shallow `dict()`, which leaves the nested
  `FabricDataAgentToolParameters` as an Azure model object and fails with
  `Object of type FabricDataAgentToolParameters is not JSON serializable`.

## Configuration

`src/fabric-dataagent-invocations/.env`:

```bash
# ARM resource id till foundry project level
AZURE_AI_PROJECT_ID="/subscriptions/.../providers/Microsoft.CognitiveServices/accounts/<account>/projects/<project>"
# Foundry project endpoint
AZURE_AI_PROJECT_ENDPOINT="https://<resource>.services.ai.azure.com/api/projects/<project>"
# Model deployment name in foundry
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"

# The Fabric connection name. Combined with AZURE_AI_PROJECT_ID to form the
# connection's ARM id, so no API call is needed.
FABRIC_CONNECTION_NAME="my-fabric-connection"
```

`AZURE_AI_PROJECT_ID` is what makes the no-API-call path work. If it is absent,
the agent falls back to an SDK lookup against `AZURE_AI_PROJECT_ENDPOINT`, which
requires permission to read project connections.

## 1. Run it directly

```bash
# be in directory
cd hosted-agent-invocations

# Git Bash rewrites values starting with /subscriptions/... into
# C:/Program Files/Git/subscriptions/... when launching a native Windows
# process. Set this before exporting AZURE_AI_PROJECT_ID.
export MSYS_NO_PATHCONV=1

# read .env and login
set -a
source src/fabric-dataagent-invocations/.env
set +a

az login --tenant "$TENANT_ID" --use-device-code

python src/fabric-dataagent-invocations/main.py
```

`main.py` calls `load_dotenv()` itself, so sourcing `.env` is only needed for
`$TENANT_ID` in the `az login` line above. Note that `load_dotenv()` does **not**
override variables already present in the environment - an exported (and
possibly mangled) value wins over the file.

It listens on `http://localhost:8088` (or `$PORT`). The route is `/invocations`
and the body shape is defined by `handle_invoke` in this sample, **not** by the
platform. From another terminal:

```bash
# non-streaming -> {"response": "..."}
curl -X POST "http://localhost:8088/invocations?agent_session_id=demo" \
  -H "Content-Type: application/json" \
  -d '{"message": "which month had highest travel rides and which month had lowest"}'

# streaming -> SSE text chunks
curl -N -X POST "http://localhost:8088/invocations?agent_session_id=demo" \
  -H "Content-Type: application/json" \
  -d '{"message": "and what was the total?", "stream": true}'
```

Reusing the same `agent_session_id` keeps the conversation in the same
`AgentSession`, so the follow-up question above has the first turn as context.

## 2. Wire up azd

`azure.yaml` and `.agentignore` are already here. Regenerate them only if you
change the agent name or the folder layout:

```bash
# Set the sys pathconv for git bash - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1

set -a
source ./src/fabric-dataagent-invocations/.env
set +a

: "${AZURE_AI_PROJECT_ID:?AZURE_AI_PROJECT_ID is missing}"
: "${AZURE_AI_PROJECT_ENDPOINT:?AZURE_AI_PROJECT_ENDPOINT is missing}"
: "${AZURE_AI_MODEL_DEPLOYMENT_NAME:?AZURE_AI_MODEL_DEPLOYMENT_NAME is missing}"

azd auth login
azd ai project set "$AZURE_AI_PROJECT_ENDPOINT"

export AZD_ENV_NAME="fabric-agentinv-dev"

rm -rf azure.yaml

azd ai agent init \
  --no-prompt --force \
  --agent-name fabric-dataagent-invocations \
  -e "$AZD_ENV_NAME" \
  --protocol invocations \
  --project-id "$AZURE_AI_PROJECT_ID" \
  --model-deployment "$AZURE_AI_MODEL_DEPLOYMENT_NAME" \
  --src ./src/fabric-dataagent-invocations \
  --deploy-mode code \
  --runtime python_3_13 \
  --entry-point main.py

# init hardcodes the endpoint; swap it for the placeholder
sed -i "s|endpoint: $AZURE_AI_PROJECT_ENDPOINT|endpoint: \${AZURE_AI_PROJECT_ENDPOINT}|" azure.yaml

# Manually modify the generated azure.yaml to include required environment variables in the `env` section (if required)
env:
  AZURE_AI_MODEL_DEPLOYMENT_NAME: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
  FABRIC_CONNECTION_NAME: ${FABRIC_CONNECTION_NAME}
  AZURE_AI_PROJECT_ID: ${AZURE_AI_PROJECT_ID}
```

Whether or not you regenerate, the azd environment must carry every variable
referenced by the `env:` block in `azure.yaml`:

```bash
azd env new "$AZD_ENV_NAME" 2>/dev/null || azd env select "$AZD_ENV_NAME"

azd env set AZURE_AI_PROJECT_ID            "$AZURE_AI_PROJECT_ID"            -e "$AZD_ENV_NAME"
azd env set AZURE_AI_PROJECT_ENDPOINT      "$AZURE_AI_PROJECT_ENDPOINT"      -e "$AZD_ENV_NAME"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "$AZURE_AI_MODEL_DEPLOYMENT_NAME" -e "$AZD_ENV_NAME"
azd env set FABRIC_CONNECTION_NAME         "$FABRIC_CONNECTION_NAME"         -e "$AZD_ENV_NAME"

azd env get-values
azd ai agent doctor --local-only
```

## 3. Run through the agent host

```bash
azd ai agent run
```

In another terminal:

```bash
azd ai agent invoke --local '{"message": "which month had highest travel rides and which month had lowest"}'
```

## 4. Deploy

```bash
az login --tenant "$TENANT_ID" --use-device-code
azd auth login

azd deploy -e "$AZD_ENV_NAME"
```

## 5. Verify the deployed agent

```bash
azd ai agent show fabric-dataagent-invocations
```

## 5.1. Invoke the deployed agent

```bash
# shell 1: stream logs
azd ai agent monitor --follow

# shell 2: invoke
azd ai agent invoke fabric-dataagent-invocations '{"message": "which month had highest travel rides and which month had lowest"}'
```

After deployment you can also invoke it from the Foundry **Agent Playground**,
watch **Log Stream**, and inspect the per-session execution under **Traces**.

> Unlike the Responses variant, this agent's request body is defined by
> `handle_invoke` (`{"message": ..., "stream": ...}`), not by the platform. If
> `azd ai agent invoke` sends a different shape, call the deployed
> `/invocations` endpoint directly with the same `curl` used in step 1.

## Troubleshooting

> For deeper probing of a deployed container - identity claims, connection
> access, and outbound reachability - deploy `main_diag.py` instead of
> `main.py`. See [diagnostics.md](./diagnostics.md).

### `CapacityNotActive ... Capacity <guid> is not active`

The Fabric capacity backing the data agent's workspace is paused. Resume it:

```bash
az resource list --resource-type 'Microsoft.Fabric/capacities' --query "[].id" -o tsv \
  | xargs -I{} az resource show --ids {} --query "{name:name, state:properties.state}" -o tsv
```

This is unrelated to the agent code - the same failure hits local runs.

### `No CustomKeys connection found for AzureFabric`

The deployed agent returns this inside the SSE stream while the HTTP call itself
succeeds with `200 OK`. For some issues, the container never reaches Fabric at all.

That matches how the tool works. `FoundryChatClient.get_fabric_tool()` returns a
*declaration only*, with no callable - the container just names the connection.
Foundry resolves it and calls Fabric server-side, so every part of the failure
happens after the request leaves this code.

The local samples in the parent folder work against the same connection, because
a signed-in user produces a valid OBO token where the hosted agent's managed
identity does not. The Fabric docs state that **service principal authentication
is not supported** for the data agent, and a hosted agent's managed identity is a
service principal.

**If you hit this:** use the local shapes
([`fabric_local_agent.py`](../fabric_local_agent.py), the prompt agent, or the
sequential workflow) which are verified working, and raise the hosted case with
support quoting the failing trace id and the OBO 400.

Note the docs' "Hosted agents" pivot describes an *ephemeral, in-process* agent
(what this sample does when run locally). It does not demonstrate a
deployed-to-Foundry container using the Fabric tool.


## Notes

The Fabric tool uses identity passthrough (On-Behalf-Of). For **local** runs the
signed-in user's identity reaches Fabric, so whoever runs it needs read access to
the published Fabric data agent - the same requirement
`diagnose_fabric_connection.py` checks.

For the **deployed** agent this is where it breaks: the OBO exchange fails with a
400 before Fabric is reached. See
[`No CustomKeys connection found for AzureFabric`](#no-customkeys-connection-found-for-azurefabric).

`azd extension list --installed` may report `azure.ai.agents` as
`Incompatible`. Check that the installed extension version and your `azd`
version line up before assuming a deploy failure is in this code.
