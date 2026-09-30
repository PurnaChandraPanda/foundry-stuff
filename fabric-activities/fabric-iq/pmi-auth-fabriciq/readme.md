
Activties are planned for local or prompt agents into Fabric data agent via Fabric IQ MCP - with ProjectManagedIdentity as remote tool auth type. Any authenticated user would start agent on client side. The authentication flow would be like following.

```
[user] -> [local or prompt agent] -> [toolbox] ------{RemoteTool authType: ProjectManagedIdentity}----> [fabric iq mcp server] -> [fabric data agent]
```

The caller needs permission to create or update project connections, such as
`Foundry Project Manager`. The project's system-assigned managed identity must
be enabled. `ProjectManagedIdentity` uses that identity for downstream calls,
not the caller's identity, or an account-level identity.

Rename the `.env.example` as `.env` file and supply correct values for specified KEYs.

## 1. Create the Fabric IQ connection

```bash
# Git Bash rewrites values starting with /subscriptions/... into
# C:/Program Files/Git/subscriptions/... when launching a native Windows
# process. Set this before exporting AZURE_AI_PROJECT_ID.
export MSYS_NO_PATHCONV=1

./create_fabric_iq_connection.sh
```

The script creates or updates this payload through the
`2025-10-01-preview` ARM API:

```json
{
  "properties": {
    "category": "RemoteTool",
    "authType": "ProjectManagedIdentity",
    "target": "<Fabric MCP endpoint>",
    "audience": "https://api.fabric.microsoft.com"
  }
}
```

The Azure CLI sign-in authorizes connection management only. Foundry acquires
the downstream token using the project identity; no client secret is stored on
this connection. The audience is a resource identifier, without `/.default`.
URL derivation reuses [the parent configuration module](../fabric_iq_config.py).

## 2. Verify configuration and runtime separately

The script reads the saved connection back and prints `category`, `authType`,
`target`, and `audience`. Confirm `authType` is `ProjectManagedIdentity`.

To test runtime authentication, invoke a Foundry agent or toolbox that references
this connection. Every downstream call uses the same project identity rather
than each user's Fabric permissions. Only allow trusted callers access to that
agent/toolbox.

```bash
python diagnose_fabric_iq_connection.py
```

See [Data agent as an MCP server](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-mcp-server)
for MCP authentication and capacity prerequisites, and
[Service principal authentication](https://learn.microsoft.com/en-us/fabric/data-science/data-agent-service-principal)
for SP setup and limitations. Use the MCP-specific scope above for this endpoint;
the general SP guide documents a different scope for the data agent query API.

## 3. Run a local agent directly against Fabric MCP

```bash
python local_fabriciq_direct_agent.py
```

This route uses the current user to call Fabric MCP directly and `FoundryChatClient` for
model inference. The current user needs both model-invocation permission and access to the Fabric data sources.

Set `ALLOWED_TOOLS` to a JSON array of exact names from the diagnostic:

```bash
ALLOWED_TOOLS='["DataAgent_DA_DataAgent_WH"]'
```

## 4. Create Toolbox in Foundry

```bash
# Publish a toolbox version holding the Fabric IQ tool
python create_fabric_iq_toolbox.py

# See what is already published
python create_fabric_iq_toolbox.py --list
```

## 5. Local agent calling Foundry Toolbox

```bash
# Run a local agent against the latest published version
python local_fabriciq_toolbox_agent.py

# Ask something else, or pin an older version
python local_fabriciq_toolbox_agent.py --query "how many total trips are there"
python local_fabriciq_toolbox_agent.py --toolbox-version 1
```

## 6. Prompt agent calling Foundry Toolbox

```bash
# Create Fabric IQ prompt agent with local user, but remote fabric iQ call via PMIe
python create_fabric_iq_prompt_agent.py

# Run Fabric IQ prompt agent with local user, but remote fabric iQ call via PMIe
python run_fabric_iq_prompt_agent.py
```
