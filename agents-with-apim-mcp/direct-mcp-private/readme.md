# Private-route APIM: direct MCP, no toolbox

This copy is isolated from the working public-APIM setup in `../direct-mcp`.
No credentials, azd state, or deployed identity IDs were copied. Populate new
configuration files from the templates; do not copy the public `.env` wholesale.
Use the private APIM's key, configured subscription header, actual MCP URL, and
backend deployment name. The `gpt-4o` examples below require that deployment on
your private backend; replace it if necessary.

Default resource names are `private-route-apim-mcp` (connection),
`private-route-apim-prompt` (prompt agent), and `private-route-apim-hosted`
(hosted agent), with azd environment `apim-private-dev`. Do not reuse the public
deployment's `private-apim-direct-hosted` name or its runtime role assignment.
Clear stale exported settings or use a fresh terminal when switching folders:
Python's environment variables take precedence over the selected `.env`.

Three agent options use private APIM without a Foundry toolbox:

| Option | MCP execution | Code |
| --- | --- | --- |
| Native prompt agent | Foundry calls APIM using `MCPTool` | [create](./create_prompt_agent.py), [run](./run_prompt_agent.py) |
| Local MAF | Python calls APIM using `MCPStreamableHTTPTool` | [local_agent.py](./local_agent.py), [maf_agent.py](./maf_agent.py) |
| Hosted MAF | Hosted Python calls APIM using `MCPStreamableHTTPTool` | [hosted-agent](./hosted-agent/readme.md) |

The native prompt option is not client-executed Python. Foundry still needs
private access to APIM. Local MAF uses your VPN; hosted MAF needs hosted outbound
VNet access. See the [shared networking guide](../readme.md#network-requirements).

## 1. Configure in your active venv

From the sample root:

```bash
cd direct-mcp-private
cp .env.example .env
```

Edit `.env`, using [.env.example](./.env.example) as the template:

- `AZURE_TENANT_ID`: tenant GUID for the Foundry resource; used for Azure CLI login.
- `AZURE_AI_PROJECT_ID`: full project ARM resource ID for connection creation.
- `AZURE_AI_PROJECT_ENDPOINT`: full Foundry project data-plane endpoint.
- `AZURE_AI_MODEL_DEPLOYMENT_NAME`: model deployment name, not model family.
- `APIM_MCP_URL`: actual Streamable HTTP Server URL from APIM's MCP Servers blade.
- `APIM_SUBSCRIPTION_KEY`: local agent and connection-creation subscription key.
- `APIM_SUBSCRIPTION_KEY_HEADER`: configured APIM header name.
- `APIM_ALLOWED_TOOLS`: exact comma-separated names, after discovery.
- Prompt agent/connection name and version as described below.

Keep using your existing `.maf_venv`. Only if dependencies are missing:

```bash
python -m pip install -r requirements.txt
```

`az login` must target the correct tenant/subscription. Local scripts use
`AzureCliCredential`. Venv activation does not sign you into Azure.

## 2. Discover private MCP tools

```bash
python diagnose_mcp.py
```

[diagnose_mcp.py](./diagnose_mcp.py) resolves DNS, verifies TLS, initializes MCP,
and paginates `tools/list`. It sends but does not print your key and does not
execute tools. It proves connectivity from this Python process only.

Confirm the resolved addresses match your intended private APIM endpoint.
Keep the gateway hostname in the URL for TLS validation, not a raw private IP.
Local VPN connectivity does not prove Foundry-side private DNS or routing:
validate the native prompt executor and hosted runtime separately.

Populate `APIM_ALLOWED_TOOLS` using the returned names. No wildcard or empty
allowlist is accepted.

## 3. Run local MAF directly

```bash
python local_agent.py --query "Call createsAChatCompletion once. Set the top-level api-version argument to v1. Put model gpt-4o, messages containing the user request 'Explain private endpoints in two sentences.', and max_completion_tokens 120 INSIDE the required AzureCreateChatCompletionRequest object. Do not put those body fields at the top level."
```

This folder is direct-only; there is no `--transport` switch.

```text
A. Client PC (VPN)  ──►  B. Foundry reasoning model     [decide + build tool args]
        │                        (path stays private as Foundry is private)
        ▼
A. Client PC (VPN)  ──►  C. APIM MCP endpoint (inbound PE)   [tools/call]
                                 │
                                 ▼
                         D. Chat-completion backend (via APIM outbound PE)  [execute]
                                 │
                                 ▼
                         response ──► C ──► A ──► (back to B for final wording)
```

Every tool call requires approval. Review the tool/arguments and enter `y` to
approve, or anything else to deny. Conversation history is retained through
approval rounds; each invocation starts a new session.

## 4. Create and run the native prompt agent

Create the [APIM project connection](../readme.md#apim-project-connection).
A connection stores authentication; it does not imply a toolbox.

```bash
# From direct-mcp-private, run once; reads direct-mcp-private/.env.
# Set manually in your Git Bash terminal.
export MSYS_NO_PATHCONV=1

python create_prompt_agent.py

python run_prompt_agent.py --query "Call createsAChatCompletion once. Set the top-level api-version argument to v1. Put model gpt-4o, messages containing the user request 'Explain private endpoints in two sentences.', and max_completion_tokens 120 INSIDE the required AzureCreateChatCompletionRequest object. Do not put those body fields at the top level."
```

The connection script runs `az login --tenant "$AZURE_TENANT_ID"` using this
folder's `.env`, verifies the subscription tenant and project endpoint, then
creates the connection through ARM. Follow the browser/broker sign-in instructions.
It refuses to overwrite an existing connection; skip creation when reusing one.
This step needs Azure CLI, not an azd project or environment. Hosted deployment
still uses azd from its own folder.

The definition has native `MCPTool`, the APIM URL, the connection reference, an
exact allowlist, and `require_approval="always"`. No key is embedded.
The runner pins the agent version and handles multiple approval/denial rounds.
Discovery/tool/response errors are surfaced explicitly.

Creation persists a new version but does not prove APIM access. Verify actual
tool output and APIM request logs. The runner prints the response ID for
inspection; it does not automatically delete the created agent version.

## 5. Run and deploy hosted direct MAF

Follow [hosted-agent/readme.md](./hosted-agent/readme.md). It has its own
configuration, dependencies, entry point, and deployment manifest.

Unlike local MAF, the hosted sample retrieves the subscription key from the
project connection using its runtime identity. It does **not** call a toolbox.
It is gated for explicitly reviewed unattended, read-only tools; local/prompt
approvals are unchanged.

For failures, use the [shared troubleshooting guide](../readme.md#troubleshooting).
