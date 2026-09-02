# Fabric IQ as a Foundry hosted agent

Deploys the Fabric IQ agent from the parent folder as a **Foundry hosted agent**
speaking the Responses protocol.

- [`src/fabric-iq-responses/main.py`](./src/fabric-iq-responses/main.py) - the agent, wrapped in `ResponsesHostServer`
- [`azure.yaml`](./azure.yaml) - azd project manifest
- [`.agentignore`](./.agentignore) - excludes `.env` and caches from the deploy ZIP

Run every command in this document **from this folder**, not the repo root.

## Prerequisites

The Fabric IQ connection and a published **toolbox** must already exist in the
Foundry project. See the [parent readme](../readme.md) for creating the
connection, then publish the toolbox:

```bash
cd ..
python create_fabric_iq_toolbox.py
python create_fabric_iq_toolbox.py --list   # confirm a version exists
cd hosted-agent

pip install -r src/fabric-iq-responses/requirements.txt
```

## How this differs from `fabric_iq_local_agent.py`

Both build the same agent against the same toolbox. What changes in a container:

- **`DefaultAzureCredential`, not `AzureCliCredential`.** The hosted container has
  no `az` CLI; it authenticates with its managed identity.
  `DefaultAzureCredential` covers both that and your local `az login`.
- **No CLI arguments.** The local sample takes `--query` and
  `--toolbox-version`; a server takes its question from each request and resolves
  the toolbox version itself.
- **The toolbox version is resolved once, at startup**, so every request uses the
  same toolbox and a missing toolbox fails the container immediately with a clear
  message instead of surfacing as an opaque 404 on the first question.
- **The MCP URL is built inline** rather than imported from
  `fabric_iq_config.py`. Only this `src/` folder is uploaded, so a cross-folder
  import would fail at container start with `ModuleNotFoundError`.

### Why there is no `async with`

The local sample wraps the toolbox in `async with`. This one deliberately does
not, and it is not an oversight: `ResponsesHostServer.run()` calls
`asyncio.run()` internally, so the server's event loop does not exist yet when
`build_agent()` runs. Connecting the toolbox early would bind its MCP session to
a throwaway loop that the server never uses.

`Agent` connects its MCP tools on the first run instead, inside the server's own
loop, and keeps them connected for the process lifetime. So the toolbox is passed
unconnected on purpose.

### Caller identity

The Fabric IQ connection uses `UserEntraToken`, which means Fabric runs queries
as the calling user rather than as the agent. `FoundryToolbox` already stamps the
platform's per-request caller-context headers on every MCP call, so this keeps
working when hosted - no extra hook is needed here.

This is the main structural difference from the sibling
`fabric-data-agent/hosted-agent`, whose Fabric tool goes through the chat client
rather than a toolbox.

### Carried over from the local sample

- `FoundryChatClient` resolves the model **at construction**, so `model=` must go
  on the client, not on `Agent`. Otherwise: `Model is required.`
- `FoundryChatClient` reads only the `FOUNDRY_PROJECT_ENDPOINT` env var, never
  `AZURE_AI_PROJECT_ENDPOINT`, so `project_endpoint=` is passed explicitly.
  Otherwise: `Either 'project_endpoint' or 'project_client' is required`.

## Configuration

`src/fabric-iq-responses/.env`:

```bash
# Foundry project endpoint
AZURE_AI_PROJECT_ENDPOINT="https://<resource>.services.ai.azure.com/api/projects/<project>"
# Model deployment name in foundry
AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4-mini"
# Toolbox holding the Fabric IQ tool; its latest version is attached at startup
FABRIC_IQ_TOOLBOX_NAME="fabric-iq-toolbox"
```

Unlike the data agent variant, `AZURE_AI_PROJECT_ID` is not needed: this agent
addresses the toolbox by endpoint and name, never by connection ARM id.

## 1. Run it directly

```bash
cd hosted-agent

# read .env and login
set -a
source src/fabric-iq-responses/.env
set +a

az login --tenant "$TENANT_ID" --use-device-code

python src/fabric-iq-responses/main.py
```

`main.py` calls `load_dotenv()` itself, so sourcing `.env` is only needed for
`$TENANT_ID` in the `az login` line above. Note that `load_dotenv()` does **not**
override variables already present in the environment.

At startup it logs the toolbox version and MCP endpoint it resolved.

It listens on `http://localhost:8088` (or `$PORT`). From another terminal:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"conversation": {"id": "fabric-iq-1"}, "input": "which month had highest travel rides and which month had lowest"}'
```

## 2. Wire up azd

`azure.yaml` and `.agentignore` are already here. Regenerate them only if you
change the agent name or the folder layout:

```bash
export MSYS_NO_PATHCONV=1

set -a
source ./src/fabric-iq-responses/.env
set +a

: "${AZURE_AI_PROJECT_ID:?AZURE_AI_PROJECT_ID is missing}"
: "${AZURE_AI_PROJECT_ENDPOINT:?AZURE_AI_PROJECT_ENDPOINT is missing}"
: "${AZURE_AI_MODEL_DEPLOYMENT_NAME:?AZURE_AI_MODEL_DEPLOYMENT_NAME is missing}"

azd auth login
azd ai project set "$AZURE_AI_PROJECT_ENDPOINT"

export AZD_ENV_NAME="fabric-agent-dev"

rm -rf azure.yaml

azd ai agent init \
  --no-prompt --force \
  --agent-name fabric-iq-responses \
  -e "$AZD_ENV_NAME" \
  --project-id "$AZURE_AI_PROJECT_ID" \
  --model-deployment "$AZURE_AI_MODEL_DEPLOYMENT_NAME" \
  --src ./src/fabric-iq-responses \
  --deploy-mode code \
  --runtime python_3_13 \
  --entry-point main.py

# init hardcodes the endpoint; swap it for the placeholder
sed -i "s|endpoint: $AZURE_AI_PROJECT_ENDPOINT|endpoint: \${AZURE_AI_PROJECT_ENDPOINT}|" azure.yaml

# Then add the required environment variables to the generated azure.yaml:
env:
  AZURE_AI_MODEL_DEPLOYMENT_NAME: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
  FABRIC_IQ_TOOLBOX_NAME: ${FABRIC_IQ_TOOLBOX_NAME}
  AZURE_AI_PROJECT_ENDPOINT: ${AZURE_AI_PROJECT_ENDPOINT}
```

`AZURE_AI_PROJECT_ID` is only used by `azd ai agent init` to locate the project;
the running agent never reads it.

Whether or not you regenerate, the azd environment must carry every variable
referenced by the `env:` block in `azure.yaml`:

```bash
azd env new "$AZD_ENV_NAME" 2>/dev/null || azd env select "$AZD_ENV_NAME"

azd env set AZURE_AI_PROJECT_ENDPOINT      "$AZURE_AI_PROJECT_ENDPOINT"      -e "$AZD_ENV_NAME"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "$AZURE_AI_MODEL_DEPLOYMENT_NAME" -e "$AZD_ENV_NAME"
azd env set FABRIC_IQ_TOOLBOX_NAME         "$FABRIC_IQ_TOOLBOX_NAME"         -e "$AZD_ENV_NAME"

azd env get-values
azd ai agent doctor --local-only
```

## 3. Run through the agent host

```bash
azd ai agent run
```

In another terminal:

```bash
azd ai agent invoke --local "which month had highest travel rides and which month had lowest"
```

## 4. Deploy

```bash
az login --tenant "$TENANT_ID" --use-device-code
azd auth login

azd deploy -e "$AZD_ENV_NAME"
```

## 5. Verify the deployed agent

```bash
azd ai agent show fabric-iq-responses
```

### 5.1. Grant the agent's managed identity access to the project

The agent reads the toolbox at startup, so its identity needs at least
`Foundry User` role on the project.

```bash
# read `Instance Identity Client ID` from `azd ai agent show` - that is the
# agent's managed identity - and pass it as --assignee-object-id
az login --tenant "$TENANT_ID" --use-device-code

az role assignment create \
  --assignee-object-id <agent-managed-identity-object-id> \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry User" \
  --scope "$AZURE_AI_PROJECT_ID"
```

### 5.2. Invoke it

```bash
azd ai agent invoke fabric-iq-responses "which month had highest travel rides and which month had lowest"

# stream logs
azd ai agent monitor --follow
```

After deployment you can also invoke it from the Foundry **Agent Playground**,
watch **Log Stream**, and inspect the per-session execution under **Traces**.

