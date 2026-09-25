# Private APIM MCP through a Foundry toolbox

This folder keeps toolbox-specific code separate from
[direct-mcp-private](../direct-mcp-private/readme.md). It targets **private APIM MCP**.
For a public APIM gateway, use [toolbox-mcp](../toolbox-mcp/readme.md) instead.

- [create_toolbox.py](./create_toolbox.py): publish a reviewed APIM tool allowlist.
- [local_agent.py](./local_agent.py): local MAF orchestration via `FoundryToolbox`.
- [create_toolbox_connection.sh](./create_toolbox_connection.sh): create the
  prompt-agent-to-toolbox Entra connection using Azure CLI, without azd.
- [create_prompt_agent.py](./create_prompt_agent.py): create a native prompt agent
  consuming the private toolbox.
- [run_prompt_agent.py](./run_prompt_agent.py): invoke the prompt agent by name
  and approve or deny tool calls.
- [hosted-agent](./hosted-agent/readme.md): standalone hosted MAF toolbox consumer.

```text
Local or hosted MAF -> Foundry toolbox -> private APIM MCP -> backend
Foundry prompt agent -> Foundry toolbox -> private APIM MCP -> backend
```

APIM calls execute in Foundry, even when the MAF agent runs locally. The toolbox
is not a VPN or tunnel. Configure
[Foundry outbound private access](../readme.md#network-requirements).
The APIM key stays in the project connection; consumer code does not receive it.

The separate [direct prompt-agent example](../direct-mcp-private/readme.md#4-create-and-run-the-native-prompt-agent)
bypasses the toolbox. The prompt scripts in this folder use the toolbox instead.

**Private networking is a prerequisite for every path here.** Foundry toolbox
execution must resolve the APIM hostname to its private address and reach it over
HTTPS. Laptop VPN access or the hosted Python runtime's private route alone does
not supply that route. Public-toolbox success does not verify private access.

## 1. Configure

From the sample root:

```bash
cd toolbox-mcp-private
cp .env.example .env
```

Copy the template only if `.env` does not already exist; otherwise update it.
Defaults are `private-route-apim-mcp` (connection) and `private-apim-toolbox`
(toolbox), distinct from the public sample. Use the exact private APIM MCP
Server URL, including its path and trailing slash if applicable.

Keep the public and private settings separate:

| Resource | Private default |
| --- | --- |
| Downstream APIM-key connection | `private-route-apim-mcp` |
| Toolbox | `private-apim-toolbox` |
| Toolbox Entra connection | `private-apim-toolbox-mcp` |
| Prompt agent | `private-apim-toolbox-prompt` |
| Hosted agent | `private-apim-toolbox-hosted` |
| azd environment | `apim-toolbox-private-dev` |

Python uses the `.env` beside its configuration module, with exported values
taking precedence. Clear or update stale public-sample exports before switching.
Do not copy the public sample's keys, identity IDs, or azd state into this folder.

Set the Foundry project endpoint/model, APIM MCP URL, connection name, exact
reviewed tool names, and toolbox name. Reuse the connection from
[direct-mcp-private](../direct-mcp-private/readme.md) only if its project, exact
target URL, and authentication match,
or create one using [create_mcp_connection.sh](../create_mcp_connection.sh).
For connection creation, also set `AZURE_TENANT_ID` to the Foundry resource's
tenant GUID, `AZURE_AI_PROJECT_ID` to the full project ARM resource ID, plus
`APIM_SUBSCRIPTION_KEY_HEADER` and `APIM_SUBSCRIPTION_KEY`
in this folder's `.env`:

```bash
# From toolbox-mcp-private; reads toolbox-mcp-private/.env without manually sourcing it.
export MSYS_NO_PATHCONV=1  # Set manually in your Git Bash terminal.
bash ../create_mcp_connection.sh toolbox-mcp-private
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

For initial tool discovery from your VPN, use
[direct-mcp-private/diagnose_mcp.py](../direct-mcp-private/diagnose_mcp.py) with
that folder's configuration set to the same private APIM endpoint. A successful
VPN call does not prove Foundry toolbox connectivity.

## 2. Publish reviewed tools

```bash
python create_toolbox.py --allow-unattended
```

Skip creation if you already have the intended private toolbox. The first
version becomes its default; later versions must be tested and promoted
explicitly. Creating a new version alone does not change the default.

The publisher uses native `MCPToolboxTool` with your APIM connection and
allowlist, and `require_approval="never"`. It refuses to publish without the
explicit acknowledgment flag.

**Only include tools and backend permissions safe for unattended read-only
use.** The flag does not make an operation read-only. Local/hosted MAF consumers
do not implement an approval/consent UI. The prompt runner below adds approval
on the outer MCP tool; it does not alter the toolbox policy for other consumers.

## 3. Run local MAF through the toolbox

```bash
python local_agent.py --query "Call createsAChatCompletion once. Set the top-level api-version argument to v1. Put model gpt-4o, messages containing the user request 'Explain private endpoints in two sentences.', and max_completion_tokens 120 INSIDE the required AzureCreateChatCompletionRequest object. Do not put those body fields at the top level."
```

This folder is toolbox-only; there is no `--transport` switch. The local agent
uses `AzureCliCredential` and attaches:

```text
<project-endpoint>/toolboxes/<name>/mcp?api-version=v1
```

All three consumers now use the unversioned endpoint, matching the working
public sample. They follow the toolbox's promoted default version; see
[toolbox endpoint patterns](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox#get-the-toolbox-mcp-endpoint).
An existing `APIM_TOOLBOX_VERSION` in your `.env` is no longer used. If you
previously pinned a non-default version, review/promote the intended version
before switching; the new consumers will use the default instead.
Verify an actual tool result and the matching private APIM request, not just a
natural-language answer.

## 4. Create and run a prompt agent through the toolbox

Run from this folder, using your existing `.maf_venv`. There are two distinct
authentication hops:

| Hop | Setting | Authentication |
| --- | --- | --- |
| Prompt agent -> toolbox | `APIM_TOOLBOX_CONNECTION_NAME` | Entra agent identity |
| Toolbox -> private APIM | `APIM_MCP_CONNECTION_NAME` | APIM subscription key |

The second connection is already used by the publisher. Do not replace it.
The first connection targets the exact toolbox consumer URL, with audience
`https://ai.azure.com`. Add these nonsecret values to the existing `.env`:

```bash
APIM_TOOLBOX_CONNECTION_NAME="private-apim-toolbox-mcp"
APIM_PROMPT_AGENT_NAME="private-apim-toolbox-prompt"
```

### Create the toolbox Entra connection

Ensure `AZURE_TENANT_ID`, `AZURE_AI_PROJECT_ID`, `AZURE_AI_PROJECT_ENDPOINT`,
`APIM_TOOLBOX_NAME`, and `APIM_TOOLBOX_CONNECTION_NAME` are set, then run:

```bash
export MSYS_NO_PATHCONV=1
./create_toolbox_connection.sh
```

The script reads trusted Bash-compatible `.env` beside itself (LF/CRLF supported)
without manual sourcing, signs in to the explicit tenant, checks the subscription
tenant and project endpoint, checks all connection-list pages, then writes and
verifies the `RemoteTool` / `AgenticIdentityToken` connection. Azure CLI is needed;
azd and Python are not. Temporary JSON is removed on exit.

Existing connections are not overwritten. Skip this step if a matching toolbox
identity connection already exists. Do not create the same name concurrently:
ARM PUT is an upsert and the existence check is not an atomic lock.
The script does not configure private networking, assign roles, or execute tools.

### Create the prompt agent and grant runtime access

```bash
python create_prompt_agent.py
```

Creation checks the toolbox default and connection target, creates an agent
version, and prints the runtime principal ID when available. Grant that identity
**Foundry User** access on the toolbox project. A successful local run uses your
Azure CLI identity, not the prompt agent's identity.

For a user authorized to assign roles, in Git Bash:

```bash
export MSYS_NO_PATHCONV=1

set -a
source .env
set +a

az login --tenant "$AZURE_TENANT_ID"

# Use this private agent's principal/object ID, not a public agent ID or client ID.
AGENT_PRINCIPAL_ID="d2cebd79-3c8d-4480-bf57-e8e0b8bab9cf"
FOUNDRY_USER_ROLE_ID="53ca6127-db72-4b80-b1b0-d745d6d5456d"
subscription_id="${AZURE_AI_PROJECT_ID#/subscriptions/}"
subscription_id="${subscription_id%%/*}"

az role assignment create \
  --subscription "$subscription_id" \
  --assignee-object-id "$AGENT_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "$FOUNDRY_USER_ROLE_ID" \
  --scope "$AZURE_AI_PROJECT_ID"

```

Use the principal printed for this agent, or verify it in Foundry if not returned.
See [toolbox RBAC prerequisites](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/toolbox#prerequisites).
Allow role-assignment propagation before retrying. If the connection uses project
managed identity instead, grant that identity access.

### Run the prompt agent

```bash
python run_prompt_agent.py --query "Call createsAChatCompletion once. Set the top-level api-version argument to v1. Put model gpt-4o, messages containing the user request 'Explain private endpoints in two sentences.', and max_completion_tokens 120 INSIDE the required AzureCreateChatCompletionRequest object. Do not put those body fields at the top level."
```

The runner selects the latest agent version by `APIM_PROMPT_AGENT_NAME`, matching
the current public runner. It does not read `APIM_PROMPT_AGENT_VERSION`.
Avoid publishing a new agent version while an approval conversation is in progress.
The toolbox independently follows its promoted default version.

Review the displayed tool names and arguments in a private terminal; enter `y`
to approve, or anything else to deny. The runner handles up to 20 approval rounds
and surfaces discovery, call, and response failures. It does not implement OAuth
consent. Verify an `MCP call:` and matching APIM logs.

## 5. Hosted MAF through the toolbox

Continue with [hosted-agent/readme.md](./hosted-agent/readme.md). The hosted
version uses `DefaultAzureCredential` and a separate azd deployment named
`private-apim-toolbox-hosted`. Set the hosted `APIM_TOOLBOX_NAME` and
`AZURE_AI_MODEL_DEPLOYMENT_NAME` to this private toolbox and your model deployment.
It follows the private
toolbox's default version without requiring `APIM_TOOLBOX_VERSION`.
Use the separate private azd environment and run provisioning successfully before
deployment, as shown in the hosted guide.

