# Hosted MAF calling APIM MCP directly

This sample uses `MCPStreamableHTTPTool` in your hosted Python code. **No toolbox
is created or called.** This folder contains a standalone hosted implementation.

```text
Hosted Python -> Foundry project connection (read credentials at startup)
Hosted Python -> Foundry model (reasoning)
Hosted Python -> outbound VNet -> public APIM MCP (tool execution)
```

## Prerequisites

- Complete the [parent direct setup](../readme.md), including the
  [APIM connection](../../readme.md#apim-project-connection).
- Configure the hosted execution network to resolve/reach private APIM.
  Native prompt access and your laptop VPN are separate execution paths.
- Grant the hosted identity permission to **read the connection with credentials**
  and call the model. Default model/session access does not imply permission
  to read connection secrets.
- Restrict the connection/subscription and tools to approved read-only use.

The code retrieves the key with `connections.get(include_credentials=True)`,
validates that the connection target exactly equals `APIM_MCP_URL`, and selects
only the configured subscription-key header. The key is held in memory, never
printed, and never included in the source/configuration deployment. The
connection is only a credential store, not a tool execution intermediary.

The key is read once at startup. After rotating it, restart/redeploy the agent
so existing processes stop using the old value. This shared-key design is not
per-user identity delegation.

## 1. Configure

From `direct-mcp`:

```bash
cd hosted-agent
cp src/private-apim-responses/.env.example src/private-apim-responses/.env
```

Set the existing project ARM resource ID (`AZURE_AI_PROJECT_ID`), project
endpoint/model, APIM MCP URL, connection name, header name, and exact
`APIM_ALLOWED_TOOLS` in the copied configuration. Do **not** add the subscription
key itself.

After reviewing effective tool/backend permissions, set this in the copied
`src/private-apim-responses/.env` so the deployment's `source` command retains it:

```dotenv
APIM_ALLOW_UNATTENDED="true"
```

Startup fails unless this explicit acknowledgment is present. The hosted sample
uses `approval_mode="never_require"` and has no approval UI. Do not expose
write/destructive tools. The parent local/prompt agents still require approval.

Keep using the existing `.maf_venv`. Only if dependencies are missing:

```bash
python -m pip install -r src/private-apim-responses/requirements.txt
```

## 2. Run locally

From this hosted folder:

```bash
python src/public-apim-responses/main.py --local
```

The code loads `.env` next to [main.py](./src/public-apim-responses/main.py)
and binds to `127.0.0.1:8088` (or `PORT`). Existing exported variables take
precedence. `DefaultAzureCredential` uses available credentials locally; the
deployed process uses its platform identity.

From another terminal:

```bash
curl --fail-with-body http://127.0.0.1:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"conversation":{"id":"apim-direct-1"},"input":"Use the configured tool to answer your question"}'
```

Local hosting still reads the key from the connection, then calls APIM from
your machine over VPN. Do not expose this unauthenticated development server
publicly. Foundry secures the deployed endpoint.

## 3. Configure and deploy

[azure.yaml](./azure.yaml) uploads only
[src/private-apim-responses](./src/private-apim-responses), with Python 3.13,
remote dependency build, and Responses protocol 2.0.0. There are no imports
from the parent folder. Source exclusions keep `.env` and caches out.

Run all azd commands from this hosted folder:

```bash
# Set manually in your Git Bash terminal.
export MSYS_NO_PATHCONV=1  

set -a
source src/public-apim-responses/.env
set +a

: "${AZURE_AI_PROJECT_ID:?Set the existing Foundry project ARM resource ID}"
: "${AZURE_AI_PROJECT_ENDPOINT:?Set the existing Foundry project endpoint}"
: "${AZURE_AI_MODEL_DEPLOYMENT_NAME:?Set an existing model deployment name}"

azd auth login

# remove old azure.yaml
rm -rf azure.yaml

# set the azd ai project
azd ai project set "$AZURE_AI_PROJECT_ENDPOINT"

# Set the env name for azd agent to follow
export AZD_ENV_NAME="apim-direct-dev"

azd ai agent init \
  --src ./src/public-apim-responses \
  --agent-name public-apim-direct-hosted \
  --environment "$AZD_ENV_NAME" \
  --project-id "$AZURE_AI_PROJECT_ID" \
  --model-deployment "$AZURE_AI_MODEL_DEPLOYMENT_NAME" \
  --deploy-mode code \
  --runtime python_3_13 \
  --entry-point main.py \
  --no-prompt
```

Update the `azure.yaml` env:

```bash
        env:
            AZURE_AI_MODEL_DEPLOYMENT_NAME: ${AZURE_AI_MODEL_DEPLOYMENT_NAME}
            AZURE_AI_PROJECT_ENDPOINT: ${AZURE_AI_PROJECT_ENDPOINT}
            APIM_ALLOWED_TOOLS: ${APIM_ALLOWED_TOOLS}
            APIM_ALLOW_UNATTENDED: ${APIM_ALLOW_UNATTENDED}
            APIM_MCP_URL: ${APIM_MCP_URL}
            APIM_MCP_SERVER_LABEL: ${APIM_MCP_SERVER_LABEL}
            APIM_MCP_CONNECTION_NAME: ${APIM_MCP_CONNECTION_NAME}
```

Select the env and deploy agent:

```bash
azd env select $AZD_ENV_NAME

azd env set FOUNDRY_PROJECT_ENDPOINT "$AZURE_AI_PROJECT_ENDPOINT"
azd env set AZURE_AI_PROJECT_ENDPOINT "$AZURE_AI_PROJECT_ENDPOINT"
azd env set AZURE_AI_MODEL_DEPLOYMENT_NAME "$AZURE_AI_MODEL_DEPLOYMENT_NAME"
azd env set APIM_MCP_URL "$APIM_MCP_URL"
azd env set APIM_MCP_SERVER_LABEL "$APIM_MCP_SERVER_LABEL"
azd env set APIM_MCP_CONNECTION_NAME "$APIM_MCP_CONNECTION_NAME"
azd env set APIM_SUBSCRIPTION_KEY_HEADER "$APIM_SUBSCRIPTION_KEY_HEADER"
azd env set APIM_ALLOWED_TOOLS "$APIM_ALLOWED_TOOLS"
azd env set APIM_ALLOW_UNATTENDED "$APIM_ALLOW_UNATTENDED"
azd env set MCP_TIMEOUT_SECONDS "$MCP_TIMEOUT_SECONDS"

azd ai agent doctor --local-only

azd deploy public-apim-direct-hosted -e "$AZD_ENV_NAME"

azd ai agent doctor
azd ai agent show public-apim-direct-hosted
```

## 4. Grant the hosted identity access to connection credentials

The hosted agent calls `connections.get(include_credentials=True)` at startup.
If the logs report `PermissionDenied` for the following data action, the
hosted identity cannot read the APIM key stored in the Foundry connection:

```text
Microsoft.CognitiveServices/accounts/AIServices/connections/listSecrets/action
```

This happens before calling APIM. It is not an APIM subscription-header error, and granting a role to your user account or APIM's managed identity does not fix the hosted agent's permission.

The built-in **Foundry User** role includes this data action. Assign it to the hosted agent identity at the **existing project scope**, not at subscription or resource-group scope. It grants broader project data access than connection-secret reading alone.

Run the following from this folder using an Azure CLI identity authorized to
create role assignments at the project scope, such as a Role Based Access
Control Administrator:

```bash
export MSYS_NO_PATHCONV=1
: "${AZURE_AI_PROJECT_ID:?Load the existing project ARM ID from the hosted .env}"

azd ai agent show private-apim-direct-hosted

# Confirmed principal/object ID for the current deployment.
# Recheck the identity if the agent is deleted/recreated or its identity changes.
HOSTED_AGENT_PRINCIPAL_ID="69f10eaf-aa5e-4ca1-9a41-da3db747b5da"
az ad sp show --id "$HOSTED_AGENT_PRINCIPAL_ID" \
  --query '{name:displayName,objectId:id,clientId:appId}' --output json

# Foundry User / Azure AI User: use its stable role ID across display-name changes.
FOUNDRY_USER_ROLE_ID="53ca6127-db72-4b80-b1b0-d745d6d5456d"
az role assignment create \
  --assignee-object-id "$HOSTED_AGENT_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "$FOUNDRY_USER_ROLE_ID" \
  --scope "$AZURE_AI_PROJECT_ID"

az role assignment list \
  --assignee-object-id "$HOSTED_AGENT_PRINCIPAL_ID" \
  --scope "$AZURE_AI_PROJECT_ID" \
  --include-inherited \
  --query '[].{role:roleDefinitionName,principalId:principalId,scope:scope}' \
  --output table
```

Use the **object ID** returned by `az ad sp show` for
`--assignee-object-id`; do not assume an "Identity Client ID" from a status
display is the object ID. Confirm that the identity belongs to the intended
hosted agent and that the assignment's scope is the intended project.

Allow time for RBAC propagation, then restart the failed runtime or redeploy
the agent and start a fresh invocation:

## 5. Invoke and verify

```bash
azd ai agent invoke public-apim-direct-hosted "Call createsAChatCompletion once. Set the top-level api-version argument to v1. Put model gpt-4o, messages containing the user request 'Explain private endpoints in two sentences.', and max_completion_tokens 120 INSIDE the required AzureCreateChatCompletionRequest object. Do not put those body fields at the top level."

azd ai agent monitor --follow
```

