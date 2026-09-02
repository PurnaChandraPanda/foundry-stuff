# Fabric data agent as a Foundry hosted agent

Deploys the Agent Framework agent from the parent folder as a **Foundry hosted agent** speaking the Responses protocol.

- [`src/fabric-dataagent-responses/main.py`](./src/fabric-dataagent-responses/main.py) - the agent, wrapped in `ResponsesHostServer`
- [`azure.yaml`](./azure.yaml) - azd project manifest
- [`.agentignore`](./.agentignore) - excludes `.env` and caches from the deploy ZIP

Run every command in this document **from this folder**, not the repo root.

## Prerequisites

The Fabric connection must already exist in the Foundry project, and the Fabric
data agent must be **published**. See the [root readme](../readme.md) for how to
create the connection and how to diagnose it.

```bash
pip install -r src/fabric-dataagent-responses/requirements.txt
```

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

`src/fabric-dataagent-responses/.env`:

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
cd hosted-agent

# Git Bash rewrites values starting with /subscriptions/... into
# C:/Program Files/Git/subscriptions/... when launching a native Windows
# process. Set this before exporting AZURE_AI_PROJECT_ID.
export MSYS_NO_PATHCONV=1

# read .env and login
set -a
source src/fabric-dataagent-responses/.env
set +a

az login --tenant "$TENANT_ID" --use-device-code

python src/fabric-dataagent-responses/main.py
```

`main.py` calls `load_dotenv()` itself, so sourcing `.env` is only needed for
`$TENANT_ID` in the `az login` line above. Note that `load_dotenv()` does **not**
override variables already present in the environment - an exported (and
possibly mangled) value wins over the file.

It listens on `http://localhost:8088` (or `$PORT`). From another terminal:

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"conversation": {"id": "fabric-1"}, "input": "which month had highest travel rides and which month had lowest"}'
```

## 2. Wire up azd

`azure.yaml` and `.agentignore` are already here. Regenerate them only if you
change the agent name or the folder layout:

```bash
# Set the sys pathconv for git bash - to overcome /subscriptions/.. based value read issues
export MSYS_NO_PATHCONV=1

set -a
source ./src/fabric-dataagent-responses/.env
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
  --agent-name fabric-dataagent-responses \
  -e "$AZD_ENV_NAME" \
  --project-id "$AZURE_AI_PROJECT_ID" \
  --model-deployment "$AZURE_AI_MODEL_DEPLOYMENT_NAME" \
  --src ./src/fabric-dataagent-responses \
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
azd ai agent show fabric-dataagent-responses
```

## 5.1. Assign roles to the hosted agent's managed identity

Read `Instance Identity Client ID` from `azd ai agent show` - that is the agent's
managed identity object id, passed below as `--assignee-object-id`.

**`Foundry User` alone is not enough.** The Fabric connection is `CustomKeys`:
`workspace-id` and `artifact-id` live in `credentials`, which reads back as
`null` on a plain GET and is only retrievable via
`connections/listSecrets/action`. `Foundry User` grants
`Microsoft.CognitiveServices/*/read` plus `accounts/listkeys/action` (the
*account* keys action, **not** the connection secrets action), so the managed
identity can see the connection but cannot read the keys that make it usable.
The service reports that as `No CustomKeys connection found for AzureFabric`.

Assign **`Foundry Project Manager`** at project scope. Its actions include
`Microsoft.CognitiveServices/accounts/projects/*`, whose wildcard covers
`projects/connections/listSecrets/action`, and its dataActions already cover
`agents/read`:

```bash
az login --tenant "$TENANT_ID" --use-device-code

PROJECT_SCOPE="/subscriptions/d44de82a-9396-4e6c-857a-739222a9f3a1/resourceGroups/rg-pupanda/providers/Microsoft.CognitiveServices/accounts/fndry23541/projects/proj-default"

az role assignment create \
  --assignee-object-id 4215e768-2ec0-43f2-b7d8-693fc7bbbcbd \
  --assignee-principal-type ServicePrincipal \
  --role "Foundry Project Manager" \
  --scope "$PROJECT_SCOPE"

az role assignment list \
  --assignee 4215e768-2ec0-43f2-b7d8-693fc7bbbcbd \
  --all --include-inherited \
  --query "[].{role:roleDefinitionName,scope:scope}" -o table
```

Creating a role assignment needs `Microsoft.Authorization/roleAssignments/write`,
which **`Contributor` does not include** - expect `AuthorizationFailed` and ask
a subscription Owner / User Access Administrator to run it.

Caveat: `Foundry Project Manager` also carries
`Microsoft.Authorization/roleAssignments/write`, so the identity could grant
itself further access. Fine for a dev project; for anything tighter, use a
custom role whose only extra action is
`Microsoft.CognitiveServices/accounts/projects/connections/listSecrets/action`.

Why the local run works without any of this: a developer signed in with
`Contributor` has `*`, which includes `listSecrets`.

## 5.2. Invoke the agent once role is assigned

```bash
azd ai agent invoke fabric-dataagent-responses "which month had highest travel rides and which month had lowest"
```

# stream logs
azd ai agent monitor --follow
azd ai agent monitor --follow --session-id <session-id>
```

After deployment you can also invoke it from the Foundry **Agent Playground**,
watch **Log Stream**, and inspect the per-session execution under **Traces**.

## Troubleshooting

### `CapacityNotActive ... Capacity <guid> is not active`

The Fabric capacity backing the data agent's workspace is paused. Resume it:

```bash
az resource list --resource-type 'Microsoft.Fabric/capacities' --query "[].id" -o tsv \
  | xargs -I{} az resource show --ids {} --query "{name:name, state:properties.state}" -o tsv
```

This is unrelated to the agent code - the same failure hits local runs.

### `No CustomKeys connection found for AzureFabric`

Four distinct causes produce this identical message:

1. **The connection id is not an ARM id.** Building it from
   `AZURE_AI_PROJECT_ENDPOINT` yields an `https://` URL. Use
   `AZURE_AI_PROJECT_ID`.
2. **Git Bash mangled the ARM id** into `C:/Program Files/Git/subscriptions/...`.
   Export `MSYS_NO_PATHCONV=1`.
3. **The managed identity cannot read the connection's secrets.** Deployment-only,
   and the current leading cause - see section 5.1. `Foundry User` cannot call
   `connections/listSecrets`; `Foundry Project Manager` can.
4. **Fabric OBO rejects service principals.** Also deployment-only. The docs say
   *"service principal authentication isn't supported"*, and a hosted agent
   authenticates with its managed identity, which **is** a service principal.

Causes 3 and 4 look identical from the outside. Fix 3 first, since it is
actionable; if the failure survives a correct role assignment, 4 is what remains
and it is a product limitation to raise with support.

**What has been ruled out by testing**, with the deployed agent still failing:

| Attempt | Result |
| --- | --- |
| Grant the agent MI `Foundry User` at project scope | still fails |
| Forward `x-agent-foundry-call-id` (confirmed `has_call_id=True` in the container) | still fails - hypothesis disproven, hook since removed |
| Set `isSharedToAll: true` on the connection | **persists**, but still fails |
| Add the agent MI to the connection's `sharedUserList` | sticks, but still fails |
| Add the blueprint principal / client id to `sharedUserList` | still fails |

On `isSharedToAll`: it is silently ignored on **create (PUT)** and honored on
**update (PATCH)**, which is why the creation script sets it yet the resource
still reads `false`. A PATCH must include the `authType` discriminator or the
body is rejected with `Missing discriminator property [AuthType]`:

```bash
az rest --method patch \
  --url ".../connections/fabric_dataagent_basic1?api-version=2025-06-01" \
  --headers "Content-Type=application/json" \
  --body '{"properties":{"authType":"CustomKeys","isSharedToAll":true}}'
```

PATCH merges rather than replaces, so `credentials` survives - confirm with
`listSecrets`, since a plain GET always shows `null` and cannot distinguish
"preserved" from "wiped".

### Reading the identity in the container

`main.py` logs two lines that discriminate between the causes above.

At startup, the identity the container presents to Foundry:

```
Container identity -> idtyp=app oid=<mi-object-id> appid=... tid=...
```

`idtyp=user` locally under `az login`; `idtyp=app` when deployed, confirming the
service-principal condition behind cause 4.

Per request, the caller identity the platform forwards:

```
Caller -> user_id=... session_id=... call_id=... headers=[...]
```

`user_id` populated but Fabric still failing means the caller identity reaches
the agent and is lost downstream; `user_id=None` means there is no caller
identity to impersonate with.

The Fabric tool itself cannot be traced from the container: `get_fabric_tool()`
returns a declaration with no callable, so Foundry resolves the connection and
calls Fabric server-side. The container's POST to `/openai/v1/responses` returns
`200 OK` and the failure arrives inside the SSE stream.

Check `gen_ai.agent.version` in the trace against
`AGENT_..._VERSION` in `.azure/<env>/.env` before trusting an absence of these
lines - an unchanged version means the code was never redeployed.

Note the docs' "Hosted agents" pivot describes an *ephemeral, in-process* agent
(what this sample does when run locally). It does not demonstrate a
deployed-to-Foundry container using the Fabric tool.

## Notes

The Fabric tool uses identity passthrough (On-Behalf-Of). When invoked through
the deployed agent, the **caller's** identity is what reaches Fabric, so whoever
invokes it needs read access to the published Fabric data agent - the same
requirement `diagnose_fabric_connection.py` checks for local runs.

`azd extension list --installed` may report `azure.ai.agents` as
`Incompatible`. Check that the installed extension version and your `azd`
version line up before assuming a deploy failure is in this code.
