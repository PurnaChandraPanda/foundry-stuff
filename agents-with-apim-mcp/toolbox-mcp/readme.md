# Public APIM MCP through a Foundry toolbox

This folder keeps toolbox-specific code separate from
[direct-mcp](../direct-mcp/readme.md). It targets **public APIM MCP**.
For a private APIM gateway, use
[toolbox-mcp-private](../toolbox-mcp-private/readme.md) instead.

- [create_toolbox.py](./create_toolbox.py): publish a reviewed APIM tool allowlist.
- [local_agent.py](./local_agent.py): local MAF orchestration via `FoundryToolbox`.
- [create_prompt_agent.py](./create_prompt_agent.py): persist a native prompt agent
  connected to the toolbox, not directly to APIM.
- [run_prompt_agent.py](./run_prompt_agent.py): invoke a specific prompt-agent
  version and approve or deny MCP calls interactively.
- [hosted-agent](./hosted-agent/readme.md): standalone hosted MAF toolbox consumer.

```text
Local or hosted MAF -> Foundry toolbox -> public APIM MCP -> backend
Foundry prompt agent -> Foundry toolbox -> public APIM MCP -> backend
```

APIM calls execute in Foundry, even when the MAF agent runs locally. The toolbox
is not a VPN or tunnel. Foundry must be able to reach the public APIM gateway,
and APIM policies must permit the call. Public reachability does not remove
subscription-key authentication. No private route to APIM is required here;
see the [network requirements](../readme.md#network-requirements).
The APIM key stays in the project connection; consumer code does not receive it.

For a prompt agent that bypasses the toolbox and calls APIM directly, see
[direct-mcp](../direct-mcp/readme.md#4-create-and-run-the-native-prompt-agent).

## 1. Configure

From the sample root:

```bash
cd toolbox-mcp
cp .env.example .env
```

Copy the template only if `.env` does not already exist; otherwise update it.
Defaults are `public-apim-mcp` (connection) and `public-apim-toolbox` (toolbox).
Keep these separate from the private sample. Replace `<public-apim-host>` with
your public gateway hostname and use its exact MCP Server URL.

Set the Foundry project endpoint/model, APIM MCP URL, connection name, exact
reviewed tool names, and toolbox name. Reuse an existing public APIM connection
only if its project, exact target URL, and authentication match,
or create one using [create_mcp_connection.sh](../create_mcp_connection.sh).
For connection creation, also set `AZURE_TENANT_ID` to the Foundry resource's
tenant GUID, `AZURE_AI_PROJECT_ID` to the full project ARM resource ID, plus
`APIM_SUBSCRIPTION_KEY_HEADER` and `APIM_SUBSCRIPTION_KEY`
in this folder's `.env`:

```bash
# From toolbox-mcp; reads toolbox-mcp/.env without manually sourcing it.
export MSYS_NO_PATHCONV=1  # Set manually in your Git Bash terminal.
../create_mcp_connection.sh toolbox-mcp
```

The script signs in using `az login --tenant "$AZURE_TENANT_ID"`, verifies the
subscription tenant and project endpoint, then creates the connection through ARM.
Follow the browser/broker sign-in instructions. It refuses to overwrite an
existing connection. Azure CLI is required; no azd environment is needed until
hosted deployment.

Skip this step if reusing an existing connection. The publisher and agent
consumers do not read the local key; it is needed only by the connection script
and can be removed from this `.env` after creation. See the
[connection guide](../readme.md#apim-project-connection) for handling credentials.

Keep your existing `.maf_venv`. Only if dependencies are missing:

```bash
python -m pip install -r requirements.txt
```

For initial tool discovery, use
[direct-mcp/diagnose_mcp.py](../direct-mcp/diagnose_mcp.py) with the direct
folder's configuration set to the same public APIM endpoint.

## 2. Publish reviewed tools

```bash
python create_toolbox.py --allow-unattended
# Set APIM_TOOLBOX_VERSION in .env to the printed version (optional).
```

The publisher uses native `MCPToolboxTool` with your APIM connection and
allowlist, and `require_approval="never"`. It refuses to publish without the
explicit acknowledgment flag.

**Only include tools and backend permissions safe for unattended read-only
use.** The flag does not make an operation read-only. The local/hosted MAF
consumers do not implement an approval/consent UI. The prompt-agent example
below adds `require_approval="always"` on its outer MCP tool and handles approval
requests in the CLI. This does not change the toolbox policy for other consumers
or implement OAuth consent.

## 3. Run local MAF through the toolbox

```bash
python local_agent.py --query "Call createsAChatCompletion once. Set the top-level api-version argument to v1. Put model gpt-4o, messages containing the user request 'Explain private endpoints in two sentences.', and max_completion_tokens 120 INSIDE the required AzureCreateChatCompletionRequest object. Do not put those body fields at the top level."
```

This folder is toolbox-only; there is no `--transport` switch. The local agent
uses `AzureCliCredential` and attaches:

```text
<project-endpoint>/toolboxes/<name>/mcp?api-version=v1
```

The local MAF and prompt-agent examples use the unversioned consumer endpoint
and follow the toolbox's promoted default version; see
[toolbox endpoint patterns](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox#get-the-toolbox-mcp-endpoint).
Publishing a new toolbox version alone does not switch the default; promote it
explicitly. `APIM_TOOLBOX_VERSION` is still used by the separate hosted example.

## 4. Create and run a native prompt agent through the toolbox

Keep using your active `.maf_venv` and run these commands from `toolbox-mcp`.
No hosted Python deployment is needed. Your existing working toolbox and its
APIM-key connection are reused, without republishing or changing the local agent.

### Configure toolbox authentication

The prompt agent needs a **second project connection** for the first hop:

| Hop | Connection setting | Authentication |
| --- | --- | --- |
| Prompt agent -> toolbox | `APIM_TOOLBOX_CONNECTION_NAME` | Microsoft Entra agent identity |
| Toolbox -> APIM | `APIM_MCP_CONNECTION_NAME` | Existing APIM subscription key |

Create a RemoteTool connection to the exact toolbox consumer URL using
Microsoft Entra **agent identity** authentication, with audience
`https://ai.azure.com`. Do not reuse the APIM-key connection or embed a
short-lived Azure CLI token in the agent definition.

Use [create_toolbox_connection.sh](./create_toolbox_connection.sh) to create this
connection through Azure CLI/ARM, without an azd project/environment. It uses
`AgenticIdentityToken` authentication and the `https://ai.azure.com` audience.
First set these values in this folder's existing `.env`:

- `AZURE_TENANT_ID`: the tenant GUID owning the Foundry resource.
- `AZURE_AI_PROJECT_ID`: the full project ARM resource ID.
- `AZURE_AI_PROJECT_ENDPOINT`
- `APIM_TOOLBOX_NAME`: your existing toolbox name.
- `APIM_TOOLBOX_CONNECTION_NAME`: a distinct name, such as `public-apim-toolbox-mcp`.

```bash
export MSYS_NO_PATHCONV=1
./create_toolbox_connection.sh
```

Run with Bash, not `source`. The script loads the trusted Bash-compatible `.env`
beside itself (LF/CRLF supported); no manual `source .env` or venv change is
needed. The file's connection settings override stale exported values.
It signs in to the explicit tenant, checks the subscription tenant and project
endpoint, refuses existing connection names across list pages, and verifies
stored connection metadata after creation. Temporary JSON is removed on exit.
Do not create the same name concurrently: ARM PUT is an upsert and the existence
check is not an atomic lock. Azure CLI login can change its default subscription;
the script uses explicit `--subscription` on subsequent calls.

Reuse a matching connection if it already exists and skip this script. It does
not create a toolbox, modify the APIM-key connection, assign roles, or verify a
live tool call. Your identity needs project-read, connection-list, and
connection-write permissions. The Python scripts do not create connections.
The root `create_mcp_connection.sh` creates only the downstream APIM-key
connection, not this Entra connection.

Add these nonsecret values to your existing `.env` without replacing it:

```bash
APIM_TOOLBOX_CONNECTION_NAME="public-apim-toolbox-mcp"
APIM_PROMPT_AGENT_NAME="public-apim-toolbox-prompt"
APIM_PROMPT_AGENT_VERSION=""
```

The scripts also use `AZURE_AI_PROJECT_ENDPOINT`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`
(creation only), and `APIM_TOOLBOX_NAME` (creation only). They do not read the
APIM key or require `APIM_TOOLBOX_VERSION`.

### Create the agent

```bash
python create_prompt_agent.py
```

Creation checks that the toolbox has a default version and the connection
targets its exact consumer URL, then creates an immutable prompt-agent version.
Each run creates a new agent version; it does not deploy a container.

Grant the connection's **agent identity** the **Foundry User** role on the
toolbox's project before invoking. The script prints the agent principal ID
when returned by the service. Your local `az login` identity's access is not
inherited by the agent. See
[toolbox RBAC prerequisites](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox#prerequisites).
If using a project-managed-identity connection instead, grant that project
identity access rather than the agent identity.

```bash
set -a
source .env
set +a

# Confirmed principal/object ID for the current deployment.
# Recheck the identity if the agent is deleted/recreated or its identity changes.
AGENT_PRINCIPAL_ID="7a663e69-086c-41de-a4b2-6f8a02e20d89"
az ad sp show --id "$AGENT_PRINCIPAL_ID" \
  --query '{name:displayName,objectId:id,clientId:appId}' --output json

# Foundry User / Azure AI User: use its stable role ID across display-name changes.
FOUNDRY_USER_ROLE_ID="53ca6127-db72-4b80-b1b0-d745d6d5456d"
az role assignment create \
  --assignee-object-id "$AGENT_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "$FOUNDRY_USER_ROLE_ID" \
  --scope "$AZURE_AI_PROJECT_ID"

az role assignment list \
  --assignee-object-id "$AGENT_PRINCIPAL_ID" \
  --scope "$AZURE_AI_PROJECT_ID" \
  --include-inherited \
  --query '[].{role:roleDefinitionName,principalId:principalId,scope:scope}' \
  --output table
```

### Run the agent

```bash
python run_prompt_agent.py --query "Call createsAChatCompletion once. Set the top-level api-version argument to v1. Put model gpt-4o, messages containing the user request 'Explain private endpoints in two sentences.', and max_completion_tokens 120 INSIDE the required AzureCreateChatCompletionRequest object. Do not put those body fields at the top level."
```

The runner pins `APIM_PROMPT_AGENT_NAME` and `APIM_PROMPT_AGENT_VERSION` on the
initial request and every approval continuation. The **agent version is pinned**;
the **toolbox still follows its promoted default version**.

Review each displayed tool name and arguments, then enter `y` to approve.
Anything else denies the call. The runner handles repeated approval rounds
(up to 20), reports discovery/tool errors, and prints the final response ID/text.
Arguments can contain sensitive data; use a private terminal.

Verify an actual `MCP call:` and correlate it with APIM logs. Creation or a
text-only response does not prove toolbox access. For `401`/`403`, check the
toolbox connection audience and runtime identity RBAC before changing the
working downstream APIM-key connection.

## 5. Hosted MAF through the toolbox

Continue with [hosted-agent/readme.md](./hosted-agent/readme.md). The hosted
version uses `DefaultAzureCredential` and a separate azd deployment named
`public-apim-toolbox-hosted`. Set the hosted `APIM_TOOLBOX_NAME` and
`APIM_TOOLBOX_VERSION` to this public toolbox and its printed version.
Existing resources are not renamed; check your configuration before deploying
with the new public defaults.

