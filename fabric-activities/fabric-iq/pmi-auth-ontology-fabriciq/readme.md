
Activties are planned for local or prompt agents into Fabric Ontology via Fabric IQ MCP - with ProjectManagedIdentity as remote tool auth type. Any authenticated user would start agent on client side. The authentication flow would be like following.

```
[user] -> [local or prompt agent] -> [toolbox] ------{RemoteTool authType: ProjectManagedIdentity}----> [fabric iq mcp server] -> [fabric Ontology]
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



## 3. Run a local agent directly against Fabric MCP

```bash
python local_fabriciq_direct_agent.py
```

This route uses the current user to call Fabric MCP directly and `FoundryChatClient` for
model inference. The current user needs both model-invocation permission and access to the Fabric data sources.

Set `ALLOWED_TOOLS` to a JSON array of exact names from the diagnostic:

```bash
ALLOWED_TOOLS='["list_ontology_rules","list_ontology_entities"]'
```

Each tool name must be a separate JSON string. A single string such as
`"list_ontology_rules,list_ontology_entities"` matches neither tool and leaves the
agent with no tools. Remove `ALLOWED_TOOLS` to expose all discovered tools; `[]`
exposes none. An exported shell value takes precedence over `.env`.

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
python local_fabriciq_toolbox_agent.py --query "List the movies with the highest ratings from Mov
ieRating, showing film, year, and rating, sorted by rating descending."
python local_fabriciq_toolbox_agent.py --toolbox-version 1
```

## 6. Prompt agent calling Foundry Toolbox

```bash
# Create Fabric IQ prompt agent with local user, but remote fabric iQ call via PMIe
python create_fabric_iq_prompt_agent.py

# Run Fabric IQ prompt agent with local user, but remote fabric iQ call via PMIe
python run_fabric_iq_prompt_agent.py
```
